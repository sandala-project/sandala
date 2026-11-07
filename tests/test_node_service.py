from __future__ import annotations

import copy
from typing import Any

import pytest
from jsonschema import Draft7Validator, FormatChecker

from sandala.core.errors import (
    ConflictError,
    DescendantWriteForbiddenError,
    DocumentValidationError,
    FieldWriteForbiddenError,
    NodeIdAlreadyExistsError,
    NotFoundError,
    QueryValidationError,
    ValidationError,
)
from sandala.core.services.node_hooks import NodeHookRegistry
from sandala.core.services.node_service import NodeService
from sandala.core.validation.schema_validator import EntitySchemaValidator, build_effective_node_schema
from sandala.storage.errors import StorageQueryRejectedError


def _node_service(entity_repo, node_repo, module_repo=None, hook_registry=None):
    return NodeService(
        entity_repo,
        node_repo,
        module_repo or InMemoryModuleRepo(entity_repo, node_repo),
        hook_registry=hook_registry,
    )


class InMemoryEntityRepo:
    def __init__(self, schemas):
        self.schemas = copy.deepcopy(schemas)

    def get_schema(self, module, entity):
        return copy.deepcopy(self.schemas.get((module, entity)))

    def get_module_schemas(self, module):
        return {
            entity: copy.deepcopy(schema)
            for (mod, entity), schema in self.schemas.items()
            if mod == module
        }


class InMemoryNodeRepo:
    def __init__(self, by_module=None):
        self.by_module = copy.deepcopy(by_module or {})
        users_nodes = self.by_module.setdefault("users", [])
        _ensure_users_identity_fixtures(users_nodes)
        for module_nodes in self.by_module.values():
            for node in module_nodes:
                node.setdefault("owner", "11111111-1111-4111-8111-111111111111")
                node.setdefault("group", "22222222-2222-4222-8222-222222222222")
                node.setdefault(
                    "perm",
                    {
                        "owner": {"r": True, "w": True, "p": True},
                        "group": {"r": True, "w": True, "p": True},
                        "others": {"r": True, "w": True, "p": True},
                    },
                )
        self.last_pipeline = None
        self.force_insert_conflict = False
        self.force_replace_conflict = False

    def find_by_id(self, module, node_id, *, deleted=None):
        for node in self.by_module.get(module, []):
            if node.get("id") != node_id:
                continue
            if deleted is None or node.get("deleted") == deleted:
                return copy.deepcopy(node)
        return None

    def find_active_by_ids(self, module, node_ids):
        return [
            copy.deepcopy(node)
            for node in self.by_module.get(module, [])
            if node.get("id") in node_ids and node.get("deleted") is False
        ]

    def find_one(self, module, query, projection=None):
        for node in self.by_module.get(module, []):
            if _match_query(node, query):
                return copy.deepcopy(node)
        return None

    def insert_node(self, module, node):
        if self.force_insert_conflict:
            return None
        if self.find_by_id(module, node["id"]) is not None:
            return None
        self.by_module.setdefault(module, []).append(copy.deepcopy(node))
        return copy.deepcopy(node)

    def replace_node(self, module, node):
        if self.force_replace_conflict:
            return None
        items = self.by_module.setdefault(module, [])
        for idx, existing in enumerate(items):
            if existing.get("id") == node.get("id"):
                items[idx] = copy.deepcopy(node)
                return copy.deepcopy(node)
        raise AssertionError("replace_node called for missing node")

    def bulk_update_fields(self, module, updates):
        updated = 0
        by_id = {update["id"]: update["fields"] for update in updates}
        for node in self.by_module.get(module, []):
            fields = by_id.get(node.get("id"))
            if fields is None or node.get("deleted") is not False:
                continue
            node.update(copy.deepcopy(fields))
            updated += 1
        return updated

    def find_descendants(self, module, node_id):
        return [
            copy.deepcopy(node)
            for node in self.by_module.get(module, [])
            if node_id in node.get("ancestors", [])
        ]

    def find_active_subtree(self, module, node_id):
        nodes = [
            copy.deepcopy(node)
            for node in self.by_module.get(module, [])
            if node.get("deleted") is False
            and (node.get("id") == node_id or node_id in node.get("ancestors", []))
        ]
        return sorted(nodes, key=lambda node: (node.get("depth", 0), node.get("id", "")))

    def update_descendants_hierarchy(self, module, node_id, new_prefix, old_prefix_len, depth_delta):
        for node in self.by_module.get(module, []):
            ancestors = node.get("ancestors", [])
            if node_id not in ancestors:
                continue
            node["ancestors"] = [*new_prefix, *ancestors[old_prefix_len:]]
            node["depth"] = node.get("depth", 0) + depth_delta

    def soft_delete_nodes(self, module, node_ids, mdate):
        node_ids_set = set(node_ids)
        modified = 0
        for node in self.by_module.get(module, []):
            if node.get("id") not in node_ids_set or node.get("deleted") is not False:
                continue
            node["deleted"] = True
            node["mdate"] = mdate
            modified += 1
        return modified

    def aggregate(self, module, pipeline):
        self.last_pipeline = copy.deepcopy(pipeline)
        nodes = [copy.deepcopy(node) for node in self.by_module.get(module, [])]
        for stage in pipeline:
            if "$match" in stage:
                nodes = [node for node in nodes if _match_query(node, stage["$match"])]
            elif "$project" in stage:
                projection = stage["$project"]
                if projection.get("_id") == 0:
                    continue
                included = [key for key, value in projection.items() if value == 1]
                if included:
                    nodes = [{key: node[key] for key in included if key in node} for node in nodes]
        return nodes


class InMemoryModuleRepo:
    def __init__(self, entity_repo: InMemoryEntityRepo, node_repo: InMemoryNodeRepo):
        self._entity_repo = entity_repo
        self._node_repo = node_repo
        self.docs: dict[str, dict[str, Any]] = {}

    def get_module(self, module: str):
        doc = self.docs.get(module)
        if doc is not None:
            return copy.deepcopy(doc)
        has_entity_schema = any(mod == module for (mod, _entity) in self._entity_repo.schemas.keys())
        has_nodes = module in self._node_repo.by_module
        if not has_entity_schema and not has_nodes:
            return None
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


def _match_query(node: dict[str, Any], expr: Any) -> bool:
    if not isinstance(expr, dict):
        return False
    if "$and" in expr and not all(_match_query(node, part) for part in expr["$and"]):
        return False
    if "$or" in expr and not any(_match_query(node, part) for part in expr["$or"]):
        return False
    if "$nor" in expr and any(_match_query(node, part) for part in expr["$nor"]):
        return False
    for key, value in expr.items():
        if key.startswith("$"):
            continue
        node_value = _get_path_value(node, key)
        if isinstance(value, dict):
            for op, op_value in value.items():
                if op == "$eq" and node_value != op_value:
                    return False
                if op == "$ne" and node_value == op_value:
                    return False
                if op == "$in" and node_value not in op_value:
                    return False
                if op == "$nin" and node_value in op_value:
                    return False
        elif isinstance(node_value, list):
            if value not in node_value:
                return False
        elif node_value != value:
            return False
    return True


def _get_path_value(doc: dict[str, Any], path: str) -> Any:
    current: Any = doc
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _book_schema():
    return {
        "title": "Book",
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            }
        },
        "required": ["name"],
        "x-meta": {
            "children": {"entities": []},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": True, "w": False, "p": False},
                    "others": {"r": True, "w": False, "p": False},
                }
            },
        },
    }


def _book_schema_with_transient_password_fields():
    schema = _book_schema()
    password_meta = {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"}
    string_meta = {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}
    password_array = {
        "type": "array",
        "items": {"type": "string", "minLength": 4, "x-meta": password_meta},
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["properties"].update(
        {
            "password": {"type": "string", "minLength": 4, "x-meta": password_meta},
            "passwords": password_array,
            "credentials": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string", "x-meta": string_meta},
                    "password": {"type": "string", "minLength": 4, "x-meta": password_meta},
                    "passwords": password_array,
                },
                "required": ["label"],
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string", "x-meta": string_meta},
                        "password": {"type": "string", "minLength": 4, "x-meta": password_meta},
                        "passwords": password_array,
                    },
                    "required": ["label"],
                    "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                },
                "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
            },
        }
    )
    return schema


def _ensure_users_identity_fixtures(users_nodes: list[dict[str, Any]]) -> None:
    required = [
        {"id": "00000000-0000-0000-0000-000000000000", "entity": "user", "deleted": False},
        {"id": "00000000-0000-0000-0000-000000000000", "entity": "group", "deleted": False},
        {"id": "11111111-1111-4111-8111-111111111111", "entity": "user", "deleted": False},
        {"id": "33333333-3333-4333-8333-333333333333", "entity": "user", "deleted": False},
        {"id": "44444444-4444-4444-8444-444444444444", "entity": "user", "deleted": False},
        {"id": "22222222-2222-4222-8222-222222222222", "entity": "group", "deleted": False},
        {"id": "33333333-3333-4333-8333-333333333333", "entity": "group", "deleted": False},
        {"id": "55555555-5555-4555-8555-555555555555", "entity": "group", "deleted": False},
    ]
    existing = {(node.get("entity"), node.get("id")) for node in users_nodes}
    for item in required:
        key = (item["entity"], item["id"])
        if key in existing:
            continue
        users_nodes.append(dict(item))


def _book_schema_with_default_perm(default_perm: dict[str, Any]):
    schema = _book_schema()
    schema["x-meta"]["perm"] = {"default": copy.deepcopy(default_perm)}
    return schema


def _users_fixture_nodes():
    return [
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "entity": "user",
            "deleted": False,
            "username": "owner",
        },
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "entity": "group",
            "deleted": False,
            "groupname": "default",
        },
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "entity": "group",
            "deleted": False,
            "groupname": "team",
        },
    ]


def _book_schema_with_write_modes():
    return {
        "title": "Book",
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
            "secret": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
            },
            "password_hash": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "none", "write-mode": "none"},
            },
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "public_note": {
                        "type": "string",
                        "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
                    },
                    "admin_note": {
                        "type": "string",
                        "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
                    },
                },
                "required": ["public_note", "admin_note"],
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            },
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {
                            "type": "string",
                            "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
                        },
                        "admin_label": {
                            "type": "string",
                            "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
                        },
                        "super_flags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "x-meta": {
                                    "semantic-type": "String",
                                    "visibility-mode": "superuser",
                                    "write-mode": "superuser",
                                },
                            },
                            "x-meta": {"semantic-type": "Array", "visibility-mode": "admin", "write-mode": "admin"},
                        },
                    },
                    "required": ["label", "admin_label", "super_flags"],
                    "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                },
                "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
            },
        },
        "required": ["name", "secret", "meta", "tags"],
        "x-meta": {
            "children": {"entities": []},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": True, "w": False, "p": False},
                    "others": {"r": True, "w": False, "p": False},
                }
            },
        },
    }


def _library_schema():
    return {
        "title": "Library",
        "description": "Library",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            }
        },
        "required": ["name"],
        "x-meta": {"children": {"entities": ["Book"]}},
    }


def _category_schema():
    return {
        "title": "Category",
        "description": "Category",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            }
        },
        "required": ["name"],
        "x-meta": {"children": {"entities": ["Category"]}},
    }


def _full_perm(owner: bool, group: bool, others: bool, *, p: bool = True):
    return {
        "owner": {"r": owner, "w": owner, "p": p if owner else False},
        "group": {"r": group, "w": group, "p": p if group else False},
        "others": {"r": others, "w": others, "p": p if others else False},
    }


def test_create_root_node_overrides_system_fields_and_generates_hierarchy():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {
            "name": "War and Peace",
            "entity": "Hacked",
            "deleted": True,
            "depth": 100,
            "ancestors": ["x"],
        },
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["entity"] == "Book"
    assert node["deleted"] is False
    assert node["depth"] == 0
    assert node["ancestors"] == []
    assert node["parent"] is None
    assert isinstance(node["id"], str)


def test_create_root_node_rejects_entity_not_allowed_in_module_root():
    entity_repo = InMemoryEntityRepo({("library", "Book"): _book_schema()})
    node_repo = InMemoryNodeRepo()
    module_repo = InMemoryModuleRepo(entity_repo, node_repo)
    module_repo.docs["library"] = {
        "name": "library",
        "description": "library",
        "root_owner": "11111111-1111-4111-8111-111111111111",
        "root_group": "22222222-2222-4222-8222-222222222222",
        "root_children_entities": ["Author"],
        "root_perm": {
            "owner": {"p": True},
            "group": {"p": True},
            "others": {"p": True},
        },
    }
    svc = _node_service(entity_repo, node_repo, module_repo)

    with pytest.raises(ValidationError, match="cannot be added to module root"):
        svc.create(
            "library",
            "Book",
            {"name": "War and Peace"},
            actor={
                "role": "superuser",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )


def test_create_root_node_allows_any_entity_when_root_children_entities_empty():
    entity_repo = InMemoryEntityRepo({("library", "Book"): _book_schema()})
    node_repo = InMemoryNodeRepo()
    module_repo = InMemoryModuleRepo(entity_repo, node_repo)
    module_repo.docs["library"] = {
        "name": "library",
        "description": "library",
        "root_owner": "11111111-1111-4111-8111-111111111111",
        "root_group": "22222222-2222-4222-8222-222222222222",
        "root_children_entities": [],
        "root_perm": {
            "owner": {"p": True},
            "group": {"p": True},
            "others": {"p": True},
        },
    }
    svc = _node_service(entity_repo, node_repo, module_repo)

    node = svc.create(
        "library",
        "Book",
        {"name": "War and Peace"},
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["entity"] == "Book"
    assert node["parent"] is None


def test_create_node_with_user_id_conflict_raises_node_id_error():
    node_id = "50000000-0000-4500-8500-000000000000"
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": node_id,
                    "entity": "Book",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2026-01-01T00:00:00Z",
                    "mdate": "2026-01-01T00:00:00Z",
                    "name": "Existing",
                }
            ]
        }
    )
    svc = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo)

    with pytest.raises(NodeIdAlreadyExistsError):
        svc.create(
            "library",
            "Book",
            {"id": node_id, "name": "New"},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )


def test_create_node_with_external_unique_index_conflict_raises_generic_conflict_error():
    repo = InMemoryNodeRepo()
    repo.force_insert_conflict = True
    svc = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo)

    with pytest.raises(ConflictError) as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "New"},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )

    assert type(exc_info.value) is ConflictError


def test_patch_node_with_external_unique_index_conflict_raises_generic_conflict_error():
    node_id = "50000000-0000-4500-8500-000000000000"
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": node_id,
                    "entity": "Book",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2026-01-01T00:00:00Z",
                    "mdate": "2026-01-01T00:00:00Z",
                    "name": "Existing",
                }
            ]
        }
    )
    repo.force_replace_conflict = True
    svc = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo)

    with pytest.raises(ConflictError) as exc_info:
        svc.patch(
            "library",
            node_id,
            {"name": "New"},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )

    assert type(exc_info.value) is ConflictError


def test_create_child_node_computes_depth_and_ancestors():
    parent = {
        "id": "lib-1",
        "entity": "Library",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2026-01-01T00:00:00Z",
        "mdate": "2026-01-01T00:00:00Z",
        "name": "Main",
    }
    svc = _node_service(
        InMemoryEntityRepo({
            ("library", "Book"): _book_schema(),
            ("library", "Library"): _library_schema(),
        }),
        InMemoryNodeRepo({"library": [parent]}),
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A", "parent": "lib-1"},
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["parent"] == "lib-1"
    assert node["depth"] == 1
    assert node["ancestors"] == ["lib-1"]


def test_create_child_denies_without_p_on_parent():
    parent = {
        "id": "lib-2",
        "entity": "Library",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, False, False, p=False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2026-01-01T00:00:00Z",
        "mdate": "2026-01-01T00:00:00Z",
        "name": "Main",
    }
    svc = _node_service(
        InMemoryEntityRepo({
            ("library", "Book"): _book_schema(),
            ("library", "Library"): _library_schema(),
        }),
        InMemoryNodeRepo({"library": [parent]}),
    )

    with pytest.raises(ValidationError, match="parent node"):
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "parent": "lib-2"},
            actor={
                "user_id": "33333333-3333-4333-8333-333333333333",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )


def test_create_node_fails_when_parent_not_found():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Parent node 'missing' not found") as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "parent": "missing"},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )
    assert exc_info.value.code == "parent_node_not_found"


def test_create_node_fails_when_parent_disallows_child_entity():
    parent = {
        "id": "author-1",
        "entity": "Author",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2026-01-01T00:00:00Z",
        "mdate": "2026-01-01T00:00:00Z",
        "name": "Leo",
    }
    author_schema = {
        "title": "Author",
        "description": "Author",
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}}},
        "required": ["name"],
        "x-meta": {
            "children": {"entities": []},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": True, "w": False, "p": False},
                    "others": {"r": True, "w": False, "p": False},
                }
            },
        },
    }
    svc = _node_service(
        InMemoryEntityRepo({
            ("library", "Book"): _book_schema(),
            ("library", "Author"): author_schema,
        }),
        InMemoryNodeRepo({"library": [parent]}),
    )

    with pytest.raises(ValidationError, match="cannot be added under parent entity 'Author'") as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "parent": "author-1"},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )
    assert exc_info.value.code == "entity_not_allowed_under_parent"


def test_patch_rejects_moving_node_to_root_when_entity_not_allowed_in_module_root():
    current = {
        "id": "book-1",
        "entity": "Book",
        "parent": "lib-1",
        "depth": 1,
        "ancestors": ["lib-1"],
        "deleted": False,
        "cdate": "2026-01-01T00:00:00Z",
        "mdate": "2026-01-01T00:00:00Z",
        "name": "Book A",
    }
    parent = {
        "id": "lib-1",
        "entity": "Library",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2026-01-01T00:00:00Z",
        "mdate": "2026-01-01T00:00:00Z",
        "name": "Main",
    }
    entity_repo = InMemoryEntityRepo({
        ("library", "Book"): _book_schema(),
        ("library", "Library"): _library_schema(),
    })
    node_repo = InMemoryNodeRepo({"library": [current, parent]})
    module_repo = InMemoryModuleRepo(entity_repo, node_repo)
    module_repo.docs["library"] = {
        "name": "library",
        "description": "library",
        "root_owner": "11111111-1111-4111-8111-111111111111",
        "root_group": "22222222-2222-4222-8222-222222222222",
        "root_children_entities": ["Library"],
        "root_perm": {
            "owner": {"p": True},
            "group": {"p": True},
            "others": {"p": True},
        },
    }
    svc = _node_service(entity_repo, node_repo, module_repo)

    with pytest.raises(ValidationError, match="cannot be added to module root") as exc_info:
        svc.patch(
            "library",
            "book-1",
            {"parent": None},
            actor={
                "role": "superuser",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )
    assert exc_info.value.code == "entity_not_allowed_in_root"

def test_create_node_fails_when_entity_schema_not_found():
    svc = _node_service(InMemoryEntityRepo({}), InMemoryNodeRepo())

    with pytest.raises(NotFoundError):
        svc.create("library", "Book", {"name": "Book A"})


def test_create_node_fails_validation_for_wrong_field_type():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Node validation failed"):
        svc.create(
            "library",
            "Book",
            {"name": 123},
            actor={"user_id": "11111111-1111-4111-8111-111111111111", "primary_group": "22222222-2222-4222-8222-222222222222"},
        )


def test_create_validates_then_removes_transient_password_values_before_persisting():
    schema = _book_schema_with_transient_password_fields()
    entity_repo = InMemoryEntityRepo({("library", "Book"): schema})
    node_repo = InMemoryNodeRepo()
    observed_before_passwords: list[str] = []
    observed_after_candidates: list[dict[str, Any]] = []
    hooks = NodeHookRegistry()

    def before_create(context):
        observed_before_passwords.append(context.payload["password"])

    def after_create(context):
        observed_after_candidates.append(context.candidate)

    hooks.register("before_create", before_create)
    hooks.register("after_create", after_create)
    svc = _node_service(entity_repo, node_repo, hook_registry=hooks)

    created = svc.create(
        "library",
        "Book",
        {
            "name": "Book A",
            "password": "root-password",
            "passwords": ["root-array-password"],
            "credentials": {
                "label": "Credentials",
                "password": "nested-password",
                "passwords": ["nested-array-password"],
            },
            "sections": [
                {
                    "label": "Section A",
                    "password": "section-password",
                    "passwords": ["section-array-password"],
                }
            ],
        },
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    stored = node_repo.find_by_id("library", created["id"], deleted=False)
    assert stored is not None
    assert observed_before_passwords == ["root-password"]
    assert "password" not in stored
    assert "passwords" not in stored
    assert stored["credentials"] == {"label": "Credentials"}
    assert stored["sections"] == [{"label": "Section A"}]
    assert observed_after_candidates == [stored]
    assert not list(
        Draft7Validator(build_effective_node_schema(schema), format_checker=FormatChecker()).iter_errors(stored)
    )


def test_password_cleanup_preserves_other_arrays_and_nullable_object_items():
    schema = _book_schema_with_transient_password_fields()
    modes = {"visibility-mode": "all", "write-mode": "all"}
    schema["properties"]["passwords"] = copy.deepcopy(schema["properties"]["passwords"])
    password_item = schema["properties"]["passwords"]["items"]
    schema["properties"]["passwords"]["items"] = {"anyOf": [{"type": "null"}, password_item]}
    object_item = schema["properties"]["sections"]["items"]
    schema["properties"]["sections"]["items"] = {"anyOf": [object_item, {"type": "null"}]}
    ordinary_arrays = {"labels": ["one", "two"], "counts": [1, 2], "flags": [False, True]}
    for name, semantic, value_type in (("labels", "String", "string"), ("counts", "Integer", "integer"),
                                      ("flags", "Boolean", "boolean")):
        schema["properties"][name] = {
            "type": "array", "x-meta": {"semantic-type": "Array", **modes},
            "items": {"type": value_type, "x-meta": {"semantic-type": semantic, **modes}},
        }
    for semantic in ("File", "Image", "Video"):
        properties = {"url": {"type": "string"}, "mime-type": {"type": "string"}, "size": {"type": "integer"}}
        if semantic == "Image":
            properties.update({"width": {"type": "integer"}, "height": {"type": "integer"}})
        name = semantic.lower() + "s"
        schema["properties"][name] = {
            "type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
                "type": "object", "additionalProperties": False, "properties": properties,
                "required": ["url"], "x-meta": {"semantic-type": semantic, **modes},
            },
        }
        ordinary_arrays[name] = [{"url": "https://example.test/asset"}]
    repo = InMemoryNodeRepo()
    svc = _node_service(InMemoryEntityRepo({("library", "Book"): schema}), repo)

    created = svc.create("library", "Book", {
        "name": "Book", "passwords": [None, "secret"],
        "sections": [None, {"label": "Section", "password": "secret", "passwords": ["secret"]}],
        **ordinary_arrays,
    }, actor={"user_id": "11111111-1111-4111-8111-111111111111",
              "primary_group": "22222222-2222-4222-8222-222222222222"})

    stored = repo.find_by_id("library", created["id"], deleted=False)
    assert "passwords" not in stored
    assert stored["sections"] == [None, {"label": "Section"}]
    assert {name: stored[name] for name in ordinary_arrays} == ordinary_arrays


@pytest.mark.parametrize(
    "value",
    [
        "anything",
        "2025-01-01T12:00:00",
        "2025-99-99T99:99:99Z",
    ],
)
def test_create_node_rejects_invalid_datetime_values(value):
    schema = _book_schema()
    schema["properties"]["published_at"] = {
        "type": "string",
        "format": "date-time",
        "x-meta": {"semantic-type": "DateTime", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("published_at")
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): schema}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(DocumentValidationError) as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "published_at": value},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )

    assert exc_info.value.details["validation_errors"][0]["path"] == ["published_at"]
    assert exc_info.value.details["validation_errors"][0]["validator"] == "format"


@pytest.mark.parametrize("value", ["2025-01-01T12:00:00Z", "2025-01-01T12:00:00+03:00"])
def test_create_node_accepts_rfc3339_datetime_values(value):
    schema = _book_schema()
    schema["properties"]["published_at"] = {
        "type": "string",
        "format": "date-time",
        "x-meta": {"semantic-type": "DateTime", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("published_at")
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): schema}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A", "published_at": value},
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["published_at"] == value


def test_create_validates_transient_password_values_before_removing_them():
    schema = _book_schema_with_transient_password_fields()
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): schema}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(DocumentValidationError) as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "password": "bad"},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )

    assert exc_info.value.details["validation_errors"][0]["path"] == ["password"]
    assert exc_info.value.details["validation_errors"][0]["validator"] == "minLength"


def test_create_node_returns_all_document_validation_errors():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(DocumentValidationError, match="Document contains multiple validation errors") as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": 123, "extra": "unexpected"},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )

    validation_errors = exc_info.value.details["validation_errors"]
    assert len(validation_errors) == 2
    assert validation_errors[0]["path"] == []
    assert validation_errors[0]["validator"] == "additionalProperties"
    assert validation_errors[1]["path"] == ["name"]
    assert validation_errors[1]["validator"] == "type"


def test_create_node_uses_non_null_branch_error_for_nullable_field():
    schema = _book_schema()
    schema["properties"]["nickname"] = {
        "anyOf": [
            {
                "type": "string",
                "minLength": 3,
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
            {"type": "null"},
        ]
    }
    schema["required"].append("nickname")
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): schema}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(DocumentValidationError, match="Node validation failed") as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "nickname": 1},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )

    validation_errors = exc_info.value.details["validation_errors"]
    assert len(validation_errors) == 1
    assert validation_errors[0]["path"] == ["nickname"]
    assert validation_errors[0]["validator"] == "type"
    assert validation_errors[0]["raw_message"] == "1 is not of type 'string'"


def test_create_rejects_field_with_admin_write_mode_for_all_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Field 'secret' is not writable for current actor") as exc_info:
        svc.create(
            "library",
            "Book",
            {
                "name": "Book A",
                "secret": "hidden",
                "meta": {"public_note": "ok", "admin_note": "hidden"},
                "tags": [{"label": "x", "admin_label": "hidden", "super_flags": ["s"]}],
            },
        )
    assert exc_info.value.code == "field_write_forbidden"


def _node_service_for_field_write(field_schema):
    schema = _book_schema()
    schema["properties"]["extra"] = field_schema
    schema = EntitySchemaValidator(lambda *_: True, lambda *_: True).validate_create_or_update(
        "library", "Book", schema
    )
    node_id = "23333333-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "name": "Existing",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
    }
    service = _node_service(
        InMemoryEntityRepo({("library", "Book"): schema}),
        InMemoryNodeRepo({"library": [existing]}),
    )
    return service, node_id


@pytest.mark.parametrize("operation", ["create", "patch"])
@pytest.mark.parametrize(("write_mode", "role", "allowed"), [
    ("all", "all", True),
    ("admin", "all", False),
    ("admin", "admin", True),
    ("superuser", "admin", False),
    ("superuser", "superuser", True),
    ("none", "superuser", False),
])
@pytest.mark.parametrize(("semantic_type", "value"), [
    ("String", "new value"),
    ("String", None),
    ("Object", {}),
    ("Object", None),
    ("Array", ["new value"]),
    ("Array", []),
    ("Array", None),
])
def test_nullable_field_write_modes_apply_to_create_and_patch(operation, write_mode, role, allowed, semantic_type, value):
    field = {
        "type": {"String": "string", "Object": "object", "Array": "array"}[semantic_type],
        "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": write_mode},
    }
    if semantic_type == "Object":
        field.update({"properties": {}, "additionalProperties": False})
    elif semantic_type == "Array":
        field["items"] = {
            "type": "string",
            "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": write_mode},
        }
    service, node_id = _node_service_for_field_write({"anyOf": [{"type": "null"}, field]})
    actor = {
        "role": role,
        "user_id": "11111111-1111-4111-8111-111111111111",
        "primary_group": "22222222-2222-4222-8222-222222222222",
    }

    def write():
        if operation == "create":
            return service.create("library", "Book", {"name": "New", "extra": value}, actor=actor)
        return service.patch("library", node_id, {"extra": value}, actor=actor)

    if allowed:
        node = write()
        stored = service._node_repo.find_by_id("library", node["id"])
        assert stored["extra"] == value
    else:
        original = copy.deepcopy(service._node_repo.by_module)
        with pytest.raises(FieldWriteForbiddenError, match="Field 'extra' is not writable"):
            write()
        assert service._node_repo.by_module == original


@pytest.mark.parametrize("operation", ["create", "patch"])
@pytest.mark.parametrize(("write_mode", "role", "allowed"), [
    ("all", "all", True),
    ("admin", "all", False),
    ("admin", "admin", True),
    ("none", "superuser", False),
])
@pytest.mark.parametrize(("layout", "expected_path"), [
    ("object", "extra.restricted"),
    ("array", "extra[1].restricted"),
    ("nested_arrays", "extra[1].team.groups[1].restricted"),
])
def test_nullable_containers_enforce_descendant_write_modes(operation, write_mode, role, allowed, layout, expected_path):
    def nullable_object(properties):
        return {"anyOf": [{
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
        }, {"type": "null"}]}

    def nullable_array(items):
        return {"anyOf": [{
            "type": "array",
            "items": items,
            "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        }, {"type": "null"}]}

    field = nullable_object({"restricted": {"anyOf": [{
        "type": "string",
        "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": write_mode},
    }, {"type": "null"}]}})
    value = {"restricted": "new value"}
    if layout == "array":
        field = nullable_array(field)
        value = [None, value]
    elif layout == "nested_arrays":
        field = nullable_array(nullable_object({"team": nullable_object({"groups": nullable_array(field)})}))
        value = [None, {"team": {"groups": [None, value]}}]
    service, node_id = _node_service_for_field_write(field)
    actor = {
        "role": role,
        "user_id": "11111111-1111-4111-8111-111111111111",
        "primary_group": "22222222-2222-4222-8222-222222222222",
    }

    def write():
        if operation == "create":
            return service.create("library", "Book", {"name": "New", "extra": value}, actor=actor)
        return service.patch("library", node_id, {"extra": value}, actor=actor)

    if allowed:
        node = write()
        stored = service._node_repo.find_by_id("library", node["id"])
        assert stored["extra"] == value
    else:
        original = copy.deepcopy(service._node_repo.by_module)
        with pytest.raises(FieldWriteForbiddenError) as exc_info:
            write()
        assert str(exc_info.value) == f"Field '{expected_path}' is not writable for current actor"
        assert service._node_repo.by_module == original


def test_create_requires_actor_defaults_when_owner_group_missing():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(
        ValidationError,
        match="Field 'owner' must be provided or actor must include non-empty user_id",
    ) as exc_info:
        svc.create("library", "Book", {"name": "Book A"})
    assert exc_info.value.code == "owner_required"


def test_create_allows_field_with_admin_write_mode_for_admin_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {
            "name": "Book A",
            "secret": "hidden",
            "meta": {"public_note": "ok", "admin_note": "admin-only"},
            "tags": [{"label": "x", "admin_label": "admin-ok", "super_flags": []}],
        },
        actor={
            "role": "admin",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["secret"] == "hidden"
    assert node["meta"]["admin_note"] == "admin-only"
    assert node["tags"][0]["admin_label"] == "admin-ok"


def test_create_rejects_nested_object_admin_field_for_all_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Field 'meta.admin_note' is not writable for current actor"):
        svc.create(
            "library",
            "Book",
            {
                "name": "Book A",
                "meta": {"public_note": "ok", "admin_note": "hidden"},
                "tags": [],
            },
        )


def test_create_allows_array_item_admin_field_for_admin_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {
            "name": "Book A",
            "secret": "hidden",
            "meta": {"public_note": "ok", "admin_note": "admin"},
            "tags": [{"label": "x", "admin_label": "hidden", "super_flags": []}],
        },
        actor={
            "role": "admin",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["tags"][0]["admin_label"] == "hidden"


def test_create_rejects_deep_array_superuser_field_for_admin_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(
        ValidationError,
        match="Field 'tags\\[0\\].super_flags\\[0\\]' is not writable for current actor",
    ):
        svc.create(
            "library",
            "Book",
            {
                "name": "Book A",
                "secret": "hidden",
                "meta": {"public_note": "ok", "admin_note": "admin-ok"},
                "tags": [{"label": "x", "admin_label": "admin-ok", "super_flags": ["root-only"]}],
            },
            actor={"role": "admin"},
        )


def test_create_allows_deep_array_superuser_field_for_superuser_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {
            "name": "Book A",
            "secret": "hidden",
            "meta": {"public_note": "ok", "admin_note": "admin-ok"},
            "tags": [{"label": "x", "admin_label": "admin-ok", "super_flags": ["root-only"]}],
        },
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["tags"][0]["super_flags"] == ["root-only"]


def test_create_rejects_none_write_mode_field_even_for_superuser_actor():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Field 'password_hash' is not writable for current actor"):
        svc.create(
            "library",
            "Book",
            {
                "name": "Book A",
                "secret": "hidden",
                "password_hash": "manual-hash",
                "meta": {"public_note": "ok", "admin_note": "admin-ok"},
                "tags": [{"label": "x", "admin_label": "admin-ok", "super_flags": ["root-only"]}],
            },
            actor={"role": "superuser"},
        )


def test_create_hook_can_fill_admin_field_for_all_actor():
    hooks = NodeHookRegistry()

    def before_hook(context):
        context.payload["secret"] = "set-by-hook"
        context.payload["meta"] = {"public_note": "ok", "admin_note": "admin-by-hook"}
        context.payload["tags"] = [{"label": "x", "admin_label": "admin-by-hook", "super_flags": []}]

    hooks.register("before_create", before_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
        hook_registry=hooks,
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A"},
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )
    stored = svc._node_repo.find_by_id("library", node["id"], deleted=False)

    assert stored is not None
    assert stored["secret"] == "set-by-hook"


def test_create_hook_can_fill_none_field_for_all_actor():
    hooks = NodeHookRegistry()

    def before_hook(context):
        context.payload["password_hash"] = "hash-from-hook"
        context.payload["secret"] = "set-by-hook"
        context.payload["meta"] = {"public_note": "ok", "admin_note": "admin-by-hook"}
        context.payload["tags"] = [{"label": "x", "admin_label": "admin-by-hook", "super_flags": []}]

    hooks.register("before_create", before_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo(),
        hook_registry=hooks,
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A"},
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
            "groups": ["22222222-2222-4222-8222-222222222222"],
            "role": "all",
        },
    )
    stored = svc._node_repo.find_by_id("library", node["id"], deleted=False)

    assert stored is not None
    assert stored["password_hash"] == "hash-from-hook"


def test_create_uses_default_perm_from_entity_schema():
    default_perm = {
        "owner": {"r": True, "w": True, "p": True},
        "group": {"r": True, "w": False, "p": False},
        "others": {"r": True, "w": False, "p": False},
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_default_perm(default_perm)}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A"},
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert node["perm"] == default_perm


def test_create_rejects_group_outside_actor_groups_for_non_superuser():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(ValidationError, match="Field 'group' must be one of actor groups") as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "group": "33333333-3333-4333-8333-333333333333"},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
                "groups": ["22222222-2222-4222-8222-222222222222"],
                "role": "all",
            },
        )
    assert exc_info.value.code == "group_not_in_actor_groups"


def test_create_allows_group_from_actor_groups_for_non_superuser():
    allowed_group = "33333333-3333-4333-8333-333333333333"
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A", "group": allowed_group},
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
            "groups": ["22222222-2222-4222-8222-222222222222", allowed_group],
            "role": "all",
        },
    )
    assert node["group"] == allowed_group


def test_create_allows_any_group_for_superuser():
    arbitrary_group = "33333333-3333-4333-8333-333333333333"
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    node = svc.create(
        "library",
        "Book",
        {"name": "Book A", "group": arbitrary_group},
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert node["group"] == arbitrary_group


def test_create_rejects_missing_owner_reference_when_users_module_exists():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"users": _users_fixture_nodes()}),
    )

    with pytest.raises(
        ValidationError,
        match="Owner 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' not found or deleted",
    ) as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "owner": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
            actor={
                "role": "superuser",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )
    assert exc_info.value.code == "owner_not_found"


def test_create_rejects_owner_not_equal_actor_for_non_superuser():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(
        ValidationError,
        match="Field 'owner' must be equal to actor.user_id for non-superuser",
    ) as exc_info:
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "owner": "44444444-4444-4444-8444-444444444444"},
            actor={
                "role": "all",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
                "groups": ["22222222-2222-4222-8222-222222222222"],
            },
        )
    assert exc_info.value.code == "owner_must_match_actor"


def test_create_skips_owner_and_group_lookup_for_matching_effective_actor():
    hooks = NodeHookRegistry()

    def before_hook(context):
        context.actor = {
            "role": "all",
            "user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "primary_group": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "groups": ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
        }
        context.payload["owner"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        context.payload["group"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    hooks.register("before_create", before_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"users": _users_fixture_nodes()}),
        hook_registry=hooks,
    )

    created = svc.create("library", "Book", {"name": "Book A"}, actor=None)
    assert created["owner"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert created["group"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_create_rejects_missing_group_reference_when_users_module_exists():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"users": _users_fixture_nodes()}),
    )

    with pytest.raises(ValidationError, match="Group 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' not found or deleted"):
        svc.create(
            "library",
            "Book",
            {"name": "Book A", "group": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
            actor={"role": "superuser", "user_id": "11111111-1111-4111-8111-111111111111"},
        )


def test_query_delegates_to_builder_and_repository():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )
    result = svc.query("library", {"project": ["name"], "filter": {"name": "A"}})
    assert isinstance(result, list)
    assert isinstance(svc._node_repo.last_pipeline, list)


def test_query_translates_storage_rejection_and_does_not_run_after_query(monkeypatch):
    hooks = NodeHookRegistry()
    service = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(), hook_registry=hooks,
    )
    error = StorageQueryRejectedError("Query contains an invalid regular expression")

    def aggregate(*args):
        raise error

    def after_query(context):
        pytest.fail("after_query must not run when execution failed")

    monkeypatch.setattr(service._node_repo, "aggregate", aggregate)
    hooks.register("after_query", after_query, module="library")
    with pytest.raises(QueryValidationError) as caught:
        service.query("library", {})
    assert caught.value.code == "query_validation_failed"
    assert caught.value.message == str(error)
    assert caught.value.__cause__ is error


def test_query_does_not_translate_unclassified_repository_errors(monkeypatch):
    service = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}), InMemoryNodeRepo(),
    )
    error = ValueError("Unexpected storage failure")

    def aggregate(*args):
        raise error

    monkeypatch.setattr(service._node_repo, "aggregate", aggregate)
    with pytest.raises(ValueError) as caught:
        service.query("library", {})
    assert caught.value is error


def test_patch_updates_node_and_ignores_system_fields():
    node_id = "11111111-1111-4111-8111-111111111111"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    patched = svc.patch(
        "library", node_id, {
            "name": "New",
            "id": "hack",
            "entity": "Hack",
            "deleted": True,
            "depth": 100,
            "ancestors": ["x"],
            "cdate": "2030-01-01T00:00:00Z",
            "mdate": "2030-01-01T00:00:00Z",
        },
    )

    assert patched["id"] == node_id
    assert patched["entity"] == "Book"
    assert patched["deleted"] is False
    assert patched["cdate"] == "2020-01-01T00:00:00Z"
    assert patched["depth"] == 0
    assert patched["ancestors"] == []
    assert patched["name"] == "New"
    assert patched["mdate"] != "2020-01-01T00:00:00Z"


def test_patch_removes_transient_password_values_added_by_before_patch_hook():
    node_id = "11111111-1111-4111-8111-111111111111"
    schema = _book_schema_with_transient_password_fields()
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    entity_repo = InMemoryEntityRepo({("library", "Book"): schema})
    node_repo = InMemoryNodeRepo({"library": [existing]})
    hooks = NodeHookRegistry()

    def before_patch(context):
        context.payload["password"] = "hook-password"

    hooks.register("before_patch", before_patch)
    svc = _node_service(entity_repo, node_repo, hook_registry=hooks)

    patched = svc.patch("library", node_id, {"name": "New"})

    stored = node_repo.find_by_id("library", node_id, deleted=False)
    assert stored is not None
    assert "password" not in stored
    assert patched["name"] == "New"
    assert not list(
        Draft7Validator(build_effective_node_schema(schema), format_checker=FormatChecker()).iter_errors(stored)
    )


def test_patch_fails_when_node_not_found():
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
    )

    with pytest.raises(NotFoundError, match="Node 'missing'"):
        svc.patch("library", "missing", {"name": "X"})


def test_patch_denies_without_w_permission():
    node_id = "22222222-2222-4222-8222-222222222229"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, False, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Write to node"):
        svc.patch(
            "library", node_id, {"name": "New"},
            actor={"user_id": "33333333-3333-4333-8333-333333333333"},
        )


def test_patch_acl_allows_owner_changing_group_and_perm_when_w_allowed():
    node_id = "22222222-2222-4222-8222-222222222228"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, False, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    result = svc.patch_acl(
        "library", node_id, {
            "group": "55555555-5555-4555-8555-555555555555",
            "perm": _full_perm(True, True, False),
        },
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "groups": ["55555555-5555-4555-8555-555555555555"],
        },
    )
    patched = result["node"]
    assert result["updated_count"] == 1
    assert patched["owner"] == "11111111-1111-4111-8111-111111111111"
    assert patched["group"] == "55555555-5555-4555-8555-555555555555"
    assert patched["perm"]["group"]["w"] is True


def test_patch_acl_rejects_owner_change_for_non_superuser_owner():
    node_id = "2a222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Field 'owner' can only be changed by superuser") as exc_info:
        svc.patch_acl(
            "library", node_id, {"owner": "44444444-4444-4444-8444-444444444444"},
            actor={
                "role": "all",
                "user_id": "11111111-1111-4111-8111-111111111111",
                "groups": ["22222222-2222-4222-8222-222222222222"],
            },
        )
    assert exc_info.value.code == "owner_change_forbidden"


def test_patch_allows_unchanged_owner_field_for_non_superuser():
    node_id = "2b222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    patched = svc.patch(
        "library", node_id,
        {"name": "New", "owner": "11111111-1111-4111-8111-111111111111"},
        actor={
            "role": "all",
            "user_id": "99999999-9999-4999-8999-999999999999",
            "groups": ["22222222-2222-4222-8222-222222222222"],
        },
    )
    assert patched["name"] == "New"
    assert patched["owner"] == existing["owner"]


def test_patch_acl_allows_non_owner_to_send_unchanged_group_and_perm():
    node_id = "2c222222-2222-4222-8222-222222222222"
    same_perm = _full_perm(False, True, True)
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    actor = {
        "role": "all",
        "user_id": "99999999-9999-4999-8999-999999999999",
        "groups": ["33333333-3333-4333-8333-333333333333"],
    }
    result = svc.patch_acl(
        "library", node_id, {
            "group": "22222222-2222-4222-8222-222222222222",
            "perm": _full_perm(False, True, True),
        },
        actor=actor,
    )

    assert result["updated_count"] == 0
    assert result["node"]["group"] == "22222222-2222-4222-8222-222222222222"
    assert result["node"]["perm"] == same_perm


def test_patch_acl_enforces_group_and_perm_rules_for_non_owner():
    node_id = "32222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, True, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    actor = {
        "user_id": "99999999-9999-4999-8999-999999999999",
        "groups": ["22222222-2222-4222-8222-222222222222"],
    }
    same_group_patch = svc.patch_acl(
        "library", node_id, {"group": "22222222-2222-4222-8222-222222222222"},
        actor=actor,
    )
    assert same_group_patch["node"]["group"] == "22222222-2222-4222-8222-222222222222"
    with pytest.raises(ValidationError, match="Field 'perm' can only be changed") as exc_info:
        svc.patch_acl("library", node_id, {"perm": _full_perm(False, False, False)}, actor=actor)
    assert exc_info.value.code == "perm_change_forbidden"


def test_patch_acl_rejects_owner_setting_group_outside_actor_groups():
    node_id = "42222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Field 'group' must be one of actor groups") as exc_info:
        svc.patch_acl(
            "library", node_id, {"group": "33333333-3333-4333-8333-333333333333"},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "groups": ["22222222-2222-4222-8222-222222222222"],
            },
        )
    assert exc_info.value.code == "group_not_in_actor_groups"


def test_patch_acl_rejects_missing_group_reference_when_users_module_exists():
    node_id = "42222222-2222-4222-8222-222222222223"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing], "users": _users_fixture_nodes()}),
    )

    missing_group = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    with pytest.raises(ValidationError, match=f"Group '{missing_group}' not found or deleted") as exc_info:
        svc.patch_acl(
            "library",
            node_id,
            {"group": missing_group},
            actor={
                "user_id": existing["owner"],
                "groups": [missing_group],
            },
        )
    assert exc_info.value.code == "group_not_found"


def test_patch_acl_allows_superuser_changing_owner_group_perm():
    node_id = "52222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, False, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    result = svc.patch_acl(
        "library", node_id, {
            "owner": "44444444-4444-4444-8444-444444444444",
            "group": "55555555-5555-4555-8555-555555555555",
            "perm": _full_perm(False, True, False),
        },
        actor={
            "role": "superuser",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert result["updated_count"] == 1
    assert result["node"]["owner"] == "44444444-4444-4444-8444-444444444444"
    assert result["node"]["group"] == "55555555-5555-4555-8555-555555555555"
    assert result["node"]["perm"]["group"]["w"] is True


def test_patch_allows_unchanged_acl_fields_and_rejects_changed_fields_before_before_patch():
    node_id = "62222222-2222-4222-8222-222222222221"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    hooks = NodeHookRegistry()
    called = []

    def before_patch(context):
        called.append(context.event)

    hooks.register("before_patch", before_patch)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
        hook_registry=hooks,
    )

    patched = svc.patch(
        "library",
        node_id,
        {
            "name": "New",
            "owner": existing["owner"],
            "group": existing["group"],
            "perm": existing["perm"],
        },
    )
    assert patched["name"] == "New"
    assert called == ["before_patch"]

    called.clear()
    with pytest.raises(ValidationError, match="ACL fields must be changed through"):
        svc.patch(
            "library",
            node_id,
            {"owner": "33333333-3333-4333-8333-333333333333"},
        )
    assert called == []


def test_before_patch_can_change_acl_fields():
    node_id = "62222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    hooks = NodeHookRegistry()

    def before_patch(context):
        context.payload["group"] = "55555555-5555-4555-8555-555555555555"
        context.actor = {
            "user_id": context.current["owner"],
            "groups": ["55555555-5555-4555-8555-555555555555"],
        }

    hooks.register("before_patch", before_patch)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
        hook_registry=hooks,
    )

    patched = svc.patch("library", node_id, {"name": "New"}, actor={"user_id": existing["owner"]})
    assert patched["name"] == "New"
    assert patched["group"] == "55555555-5555-4555-8555-555555555555"


def test_acl_hooks_are_acl_only_and_run_for_changed_node():
    node_id = "62222222-2222-4222-8222-222222222223"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    hooks = NodeHookRegistry()
    events = []

    def before_acl_patch(context):
        events.append((context.event, context.node_id))
        context.payload["perm"] = _full_perm(True, False, False)

    def after_acl_patch(context):
        events.append((context.event, context.node_id))
        assert set(context.payload) == {"perm", "mdate"}

    hooks.register("before_acl_patch", before_acl_patch)
    hooks.register("after_acl_patch", after_acl_patch)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
        hook_registry=hooks,
    )

    result = svc.patch_acl(
        "library", node_id, {"perm": _full_perm(True, True, True)},
        actor={"user_id": existing["owner"], "groups": [existing["group"]]},
    )
    assert result["updated_count"] == 1
    assert events == [("before_acl_patch", node_id), ("after_acl_patch", node_id)]

    hooks = NodeHookRegistry()

    def invalid_acl_hook(context):
        context.payload["name"] = "must not be persisted"

    hooks.register("before_acl_patch", invalid_acl_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
        hook_registry=hooks,
    )
    with pytest.raises(ValidationError, match="may only change owner, group and perm"):
        svc.patch_acl("library", node_id, {"perm": _full_perm(True, True, True)}, actor={"user_id": existing["owner"]})


def test_recursive_acl_patch_bulk_updates_subtree_and_returns_root_count():
    root_id = "62222222-2222-4222-8222-222222222224"
    child_id = "62222222-2222-4222-8222-222222222225"
    common = {
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "entity": "Book",
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Node",
    }
    root = {**common, "id": root_id, "parent": None, "depth": 0, "ancestors": []}
    child = {**common, "id": child_id, "parent": root_id, "depth": 1, "ancestors": [root_id]}
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [root, child]}),
    )

    result = svc.patch_acl(
        "library", root_id, {"perm": _full_perm(True, False, False)},
        recursive=True,
        actor={"user_id": common["owner"], "groups": [common["group"]]},
    )
    assert result["node"]["id"] == root_id
    assert result["updated_count"] == 2
    assert svc._node_repo.find_by_id("library", root_id)["perm"] == _full_perm(True, False, False)
    assert svc._node_repo.find_by_id("library", child_id)["perm"] == _full_perm(True, False, False)


def test_patch_fails_validation_for_wrong_field_type():
    node_id = "22222222-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Node validation failed"):
        svc.patch("library", node_id, {"name": 123})


def test_patch_rejects_field_with_admin_write_mode_for_all_actor():
    node_id = "23333333-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
        "secret": "s",
        "meta": {"public_note": "ok", "admin_note": "admin"},
        "tags": [{"label": "x", "admin_label": "admin", "super_flags": []}],
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Field 'secret' is not writable for current actor"):
        svc.patch("library", node_id, {"secret": "new"})


def test_patch_allows_deep_array_superuser_field_for_superuser_actor():
    node_id = "24444444-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
        "secret": "s",
        "meta": {"public_note": "ok", "admin_note": "admin"},
        "tags": [{"label": "x", "admin_label": "admin", "super_flags": []}],
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    patched = svc.patch(
        "library", node_id, {"tags": [{"label": "x", "admin_label": "admin", "super_flags": ["root-only"]}]},
        actor={"role": "superuser"},
    )

    assert patched["tags"][0]["super_flags"] == ["root-only"]


def test_patch_rejects_none_write_mode_field_even_for_superuser_actor():
    node_id = "24444444-2222-4222-8222-222222222220"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
        "secret": "s",
        "password_hash": "stored",
        "meta": {"public_note": "ok", "admin_note": "admin"},
        "tags": [{"label": "x", "admin_label": "admin", "super_flags": []}],
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        InMemoryNodeRepo({"library": [existing]}),
    )

    with pytest.raises(ValidationError, match="Field 'password_hash' is not writable for current actor"):
        svc.patch("library", node_id, {"password_hash": "manual-hash"}, actor={"role": "superuser"})


def test_patch_hook_can_fill_admin_field_for_all_actor():
    hooks = NodeHookRegistry()
    node_id = "25555555-2222-4222-8222-222222222222"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
        "secret": "s",
        "meta": {"public_note": "ok", "admin_note": "admin"},
        "tags": [{"label": "x", "admin_label": "admin", "super_flags": []}],
    }

    def before_hook(context):
        context.payload["secret"] = "set-by-hook"

    hooks.register("before_patch", before_hook)
    repo = InMemoryNodeRepo({"library": [existing]})
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        repo,
        hook_registry=hooks,
    )

    updated = svc.patch("library", node_id, {"name": "New"})
    stored = repo.find_by_id("library", node_id, deleted=False)

    assert updated["name"] == "New"
    assert stored is not None
    assert stored["secret"] == "set-by-hook"


def test_patch_hook_can_fill_none_field_for_all_actor():
    hooks = NodeHookRegistry()
    node_id = "25555555-2222-4222-8222-222222222220"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
        "secret": "s",
        "password_hash": "stored",
        "meta": {"public_note": "ok", "admin_note": "admin"},
        "tags": [{"label": "x", "admin_label": "admin", "super_flags": []}],
    }

    def before_hook(context):
        context.payload["password_hash"] = "patched-from-hook"

    hooks.register("before_patch", before_hook)
    repo = InMemoryNodeRepo({"library": [existing]})
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema_with_write_modes()}),
        repo,
        hook_registry=hooks,
    )

    updated = svc.patch("library", node_id, {"name": "New"})
    stored = repo.find_by_id("library", node_id, deleted=False)

    assert updated["name"] == "New"
    assert stored is not None
    assert stored["password_hash"] == "patched-from-hook"


def test_patch_move_rewrites_subtree_hierarchy():
    root_id = "30000000-0000-4300-8300-000000000000"
    branch_id = "30000000-0000-4300-8300-000000000001"
    moving_id = "30000000-0000-4300-8300-000000000002"
    child_id = "30000000-0000-4300-8300-000000000003"
    root = {
        "id": root_id,
        "entity": "Category",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Root",
    }
    branch = {
        "id": branch_id,
        "entity": "Category",
        "parent": root_id,
        "depth": 1,
        "ancestors": [root_id],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "A",
    }
    moving = {
        "id": moving_id,
        "entity": "Category",
        "parent": branch_id,
        "depth": 2,
        "ancestors": [root_id, branch_id],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "X",
    }
    child = {
        "id": child_id,
        "entity": "Category",
        "parent": moving_id,
        "depth": 3,
        "ancestors": [root_id, branch_id, moving_id],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Y",
    }
    repo = InMemoryNodeRepo({"library": [root, branch, moving, child]})
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
    )

    patched = svc.patch("library", moving_id, {"parent": None})
    moved_child = repo.find_by_id("library", child_id)

    assert patched["parent"] is None
    assert patched["depth"] == 0
    assert patched["ancestors"] == []
    assert moved_child["depth"] == 1
    assert moved_child["ancestors"] == [moving_id]


def test_patch_move_denies_when_no_p_on_new_parent():
    parent_id = "30000000-0000-4300-8300-000000000099"
    moving_id = "30000000-0000-4300-8300-000000000098"
    parent = {
        "id": parent_id,
        "entity": "Category",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(False, False, False, p=False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "P",
    }
    moving = {
        "id": moving_id,
        "entity": "Category",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, False, False),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "X",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        InMemoryNodeRepo({"library": [parent, moving]}),
    )

    with pytest.raises(ValidationError, match="parent node"):
        svc.patch(
            "library", moving_id, {"parent": parent_id},
            actor={
                "user_id": "11111111-1111-4111-8111-111111111111",
                "primary_group": "22222222-2222-4222-8222-222222222222",
            },
        )


def test_patch_move_fails_when_new_parent_is_descendant():
    parent_id = "40000000-0000-4400-8400-000000000000"
    child_id = "40000000-0000-4400-8400-000000000001"
    parent = {
        "id": parent_id,
        "entity": "Category",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "X",
    }
    child = {
        "id": child_id,
        "entity": "Category",
        "parent": parent_id,
        "depth": 1,
        "ancestors": [parent_id],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Y",
    }
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        InMemoryNodeRepo({"library": [parent, child]}),
    )

    with pytest.raises(ValidationError, match="cannot be a descendant"):
        svc.patch("library", parent_id, {"parent": child_id})


def test_delete_soft_deletes_node_and_descendants_only():
    root_id = "60000000-0000-4600-8600-000000000000"
    moving_id = "60000000-0000-4600-8600-000000000001"
    child_id = "60000000-0000-4600-8600-000000000002"
    sibling_id = "60000000-0000-4600-8600-000000000003"

    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": root_id,
                    "entity": "Category",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                },
                {
                    "id": moving_id,
                    "entity": "Category",
                    "parent": root_id,
                    "depth": 1,
                    "ancestors": [root_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Moving",
                },
                {
                    "id": child_id,
                    "entity": "Category",
                    "parent": moving_id,
                    "depth": 2,
                    "ancestors": [root_id, moving_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Child",
                },
                {
                    "id": sibling_id,
                    "entity": "Category",
                    "parent": root_id,
                    "depth": 1,
                    "ancestors": [root_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Sibling",
                },
            ]
        }
    )
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
    )

    deleted_count = svc.delete("library", moving_id)

    assert deleted_count == 2
    assert repo.find_by_id("library", moving_id)["deleted"] is True
    assert repo.find_by_id("library", child_id)["deleted"] is True
    assert repo.find_by_id("library", sibling_id)["deleted"] is False


def test_delete_denies_without_w_permission():
    node_id = "60000000-0000-4600-8600-000000000099"
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": node_id,
                    "entity": "Category",
                    "parent": None,
                    "owner": "11111111-1111-4111-8111-111111111111",
                    "group": "22222222-2222-4222-8222-222222222222",
                    "perm": _full_perm(False, False, False),
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                }
            ]
        }
    )
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
    )
    with pytest.raises(ValidationError, match="Write to node"):
        svc.delete(
            "library", node_id,
            actor={"user_id": "33333333-3333-4333-8333-333333333333"},
        )


def test_delete_denies_when_an_active_descendant_lacks_w_permission():
    root_id = "60000000-0000-4600-8600-000000000101"
    child_id = "60000000-0000-4600-8600-000000000102"
    actor_id = "33333333-3333-4333-8333-333333333333"
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": root_id,
                    "entity": "Category",
                    "parent": None,
                    "owner": actor_id,
                    "group": "22222222-2222-4222-8222-222222222222",
                    "perm": _full_perm(True, False, False),
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                },
                {
                    "id": child_id,
                    "entity": "Category",
                    "parent": root_id,
                    "owner": "11111111-1111-4111-8111-111111111111",
                    "group": "22222222-2222-4222-8222-222222222222",
                    "perm": _full_perm(False, False, False),
                    "depth": 1,
                    "ancestors": [root_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Child",
                },
            ]
        }
    )
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
    )

    with pytest.raises(DescendantWriteForbiddenError) as exc_info:
        svc.delete("library", root_id, actor={"user_id": actor_id})

    assert exc_info.value.code == "descendant_write_forbidden"
    assert child_id not in exc_info.value.message
    assert repo.find_by_id("library", root_id)["deleted"] is False
    assert repo.find_by_id("library", child_id)["deleted"] is False


def test_delete_fails_when_node_not_found_or_already_deleted():
    node_id = "70000000-0000-4700-8700-000000000000"
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(
            {
                "library": [
                    {
                        "id": node_id,
                        "entity": "Book",
                        "parent": None,
                        "depth": 0,
                        "ancestors": [],
                        "deleted": True,
                        "cdate": "2020-01-01T00:00:00Z",
                        "mdate": "2020-01-01T00:00:00Z",
                        "name": "Already deleted",
                    }
                ]
            }
        ),
    )

    with pytest.raises(NotFoundError, match=f"Node '{node_id}'"):
        svc.delete("library", node_id)


def test_create_dispatches_before_and_after_hooks_and_allows_payload_update():
    hooks = NodeHookRegistry()
    calls: list[tuple[str, Any]] = []

    def before_hook(context):
        calls.append(("before", context.payload["name"]))
        context.payload["name"] = "From hook"

    def after_hook(context):
        calls.append(("after", context.result["name"]))
        assert context.candidate["name"] == "From hook"

    hooks.register("before_create", before_hook)
    hooks.register("after_create", after_hook)

    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
        hook_registry=hooks,
    )

    created = svc.create(
        "library",
        "Book",
        {"name": "Original"},
        actor={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
        },
    )

    assert created["name"] == "From hook"
    assert calls == [("before", "Original"), ("after", "From hook")]


def test_before_create_hook_gets_generated_id():
    hooks = NodeHookRegistry()
    seen: dict[str, str] = {}

    def before_hook(context):
        seen["id"] = context.payload.get("id")

    hooks.register("before_create", before_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo(),
        hook_registry=hooks,
    )

    created = svc.create(
        "library",
        "Book",
        {"name": "Book A"},
        actor={
            "role": "all",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
            "groups": ["22222222-2222-4222-8222-222222222222"],
        },
    )

    assert isinstance(seen.get("id"), str)
    assert seen["id"] == created["id"]


def test_patch_dispatches_hooks_with_current_and_result_nodes():
    hooks = NodeHookRegistry()
    calls: list[str] = []
    node_id = "80000000-0000-4800-8800-000000000000"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }

    def before_hook(context):
        calls.append("before")
        assert context.current["name"] == "Old"
        context.payload["name"] = "Updated by hook"

    def after_hook(context):
        calls.append("after")
        assert context.current["name"] == "Old"
        assert context.result["name"] == "Updated by hook"

    hooks.register("before_patch", before_hook)
    hooks.register("after_patch", after_hook)

    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing]}),
        hook_registry=hooks,
    )

    updated = svc.patch("library", node_id, {"name": "Ignored"})

    assert updated["name"] == "Updated by hook"
    assert calls == ["before", "after"]


def test_patch_uses_actor_changed_in_before_patch_hook_for_acl_checks():
    hooks = NodeHookRegistry()
    node_id = "91111111-1111-4111-8111-111111111111"
    existing = {
        "id": node_id,
        "entity": "Book",
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": _full_perm(True, True, True),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        "name": "Old",
    }

    def before_hook(context):
        context.actor = {
            "role": "all",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "primary_group": "22222222-2222-4222-8222-222222222222",
            "groups": ["22222222-2222-4222-8222-222222222222"],
        }
        context.payload["group"] = "22222222-2222-4222-8222-222222222222"

    hooks.register("before_patch", before_hook)
    svc = _node_service(
        InMemoryEntityRepo({("library", "Book"): _book_schema()}),
        InMemoryNodeRepo({"library": [existing], "users": _users_fixture_nodes()}),
        hook_registry=hooks,
    )

    patched = svc.patch("library", node_id, {"name": "New"}, actor={"role": "all"})
    assert patched["name"] == "New"


def test_delete_dispatches_scoped_hooks_only_for_matching_module_and_entity():
    hooks = NodeHookRegistry()
    calls: list[str] = []
    node_id = "90000000-0000-4900-8900-000000000000"
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": node_id,
                    "entity": "Category",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                }
            ]
        }
    )

    def matching_before(context):
        calls.append("before")

    def matching_after(context):
        calls.append(f"after:{context.deleted_count}")

    def other_entity_hook(context):
        calls.append("wrong")

    hooks.register("before_delete", matching_before, module="library", entity="Category")
    hooks.register("after_delete", matching_after, module="library", entity="Category")
    hooks.register("before_delete", other_entity_hook, module="library", entity="Book")

    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
        hook_registry=hooks,
    )

    deleted_count = svc.delete("library", node_id)

    assert deleted_count == 1
    assert calls == ["before", "after:1"]


def test_delete_dispatches_hooks_for_every_node_in_subtree_before_bulk_delete():
    root_id = "90000000-0000-4900-8900-000000000010"
    child_id = "90000000-0000-4900-8900-000000000011"
    calls: list[str] = []
    hooks = NodeHookRegistry()
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": root_id,
                    "entity": "Category",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                },
                {
                    "id": child_id,
                    "entity": "Book",
                    "parent": root_id,
                    "depth": 1,
                    "ancestors": [root_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Child",
                },
            ]
        }
    )

    hooks.register("before_delete", lambda context: calls.append(f"before:{context.node_id}"), module="library")
    hooks.register(
        "after_delete",
        lambda context: calls.append(f"after:{context.node_id}:{context.deleted_count}"),
        module="library",
    )
    svc = _node_service(
        InMemoryEntityRepo(
            {
                ("library", "Category"): _category_schema(),
                ("library", "Book"): _book_schema(),
            }
        ),
        repo,
        hook_registry=hooks,
    )

    assert svc.delete("library", root_id) == 2
    assert calls == [
        f"before:{root_id}",
        f"before:{child_id}",
        f"after:{root_id}:2",
        f"after:{child_id}:2",
    ]


def test_delete_hook_failure_for_descendant_aborts_bulk_delete():
    root_id = "90000000-0000-4900-8900-000000000020"
    child_id = "90000000-0000-4900-8900-000000000021"
    hooks = NodeHookRegistry()
    repo = InMemoryNodeRepo(
        {
            "library": [
                {
                    "id": root_id,
                    "entity": "Category",
                    "parent": None,
                    "depth": 0,
                    "ancestors": [],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Root",
                },
                {
                    "id": child_id,
                    "entity": "Category",
                    "parent": root_id,
                    "depth": 1,
                    "ancestors": [root_id],
                    "deleted": False,
                    "cdate": "2020-01-01T00:00:00Z",
                    "mdate": "2020-01-01T00:00:00Z",
                    "name": "Child",
                },
            ]
        }
    )

    def reject_child(context):
        if context.node_id == child_id:
            raise ConflictError("Child cannot be deleted")

    hooks.register("before_delete", reject_child, module="library")
    svc = _node_service(
        InMemoryEntityRepo({("library", "Category"): _category_schema()}),
        repo,
        hook_registry=hooks,
    )

    with pytest.raises(ConflictError, match="Child cannot be deleted"):
        svc.delete("library", root_id)

    assert repo.find_by_id("library", root_id)["deleted"] is False
    assert repo.find_by_id("library", child_id)["deleted"] is False


def test_default_read_project_resolves_schema_links_owner_and_group_only():
    service = _node_service(InMemoryEntityRepo({}), InMemoryNodeRepo())
    schema = {
        "type": "object",
        "properties": {
            "author": {
                "type": "string",
                "x-meta": {"semantic-type": "Link"},
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "editors": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "x-meta": {"semantic-type": "LinkArray"},
                        },
                    }
                },
            },
            "nullable_link": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "x-meta": {"semantic-type": "Link"}},
                ]
            },
        },
    }

    project = service._build_default_read_project(schema)

    assert project == ["*", "owner.*", "group.*", "author.*", "metadata.editors.*", "nullable_link.*"]
    assert "parent.*" not in project
    assert "ancestors.*" not in project


def test_default_read_project_resolves_only_links_visible_to_actor():
    service = _node_service(InMemoryEntityRepo({}), InMemoryNodeRepo())
    schema = {
        "type": "object",
        "properties": {
            "public_link": {
                "type": "string",
                "x-meta": {"semantic-type": "Link", "visibility-mode": "all"},
            },
            "admin_link": {
                "type": "string",
                "x-meta": {"semantic-type": "Link", "visibility-mode": "admin"},
            },
            "never_link": {
                "type": "string",
                "x-meta": {"semantic-type": "Link", "visibility-mode": "none"},
            },
            "admin_container": {
                "type": "object",
                "x-meta": {"semantic-type": "Object", "visibility-mode": "admin"},
                "properties": {
                    "link": {
                        "type": "string",
                        "x-meta": {"semantic-type": "Link", "visibility-mode": "all"},
                    },
                },
            },
            "hidden_nested_link": {
                "type": "object",
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all"},
                "properties": {
                    "link": {
                        "type": "string",
                        "x-meta": {"semantic-type": "Link", "visibility-mode": "admin"},
                    },
                },
            },
        },
    }

    assert service._build_default_read_project(schema) == ["*", "owner.*", "group.*", "public_link.*"]
    assert service._build_default_read_project(schema, actor={"role": "admin"}) == [
        "*",
        "owner.*",
        "group.*",
        "public_link.*",
        "admin_link.*",
        "admin_container.link.*",
        "hidden_nested_link.link.*",
    ]
    assert "never_link.*" not in service._build_default_read_project(schema, actor={"role": "superuser"})


def test_get_scopes_read_to_actual_entity_and_uses_default_project():
    schema = _book_schema()
    repo = InMemoryNodeRepo({"library": [{"id": "book-1", "entity": "Book", "deleted": False}]})
    service = _node_service(InMemoryEntityRepo({("library", "Book"): schema}), repo)
    calls: list[dict[str, Any]] = []
    reads = []
    find_one = repo.find_one

    def read(module, query, projection=None):
        reads.append((module, query, projection))
        return find_one(module, query, projection)

    repo.find_one = read

    def query(module, payload, *, actor=None):
        calls.append(copy.deepcopy(payload))
        return [{"id": "book-1", "entity": "Book"}]

    service.query = query

    result = service.get("library", "book-1")

    assert result["id"] == "book-1"
    assert reads == [(
        "library", {"id": "book-1", "deleted": False},
        {"_id": 0, "entity": 1, "owner": 1, "group": 1, "perm": 1},
    )]
    assert calls == [
        {
            "filter": {"id": "book-1", "entity": "Book"},
            "project": ["*", "owner.*", "group.*"],
        },
    ]


def test_get_passes_explicit_wildcard_string_to_query_builder():
    schema = _book_schema()
    repo = InMemoryNodeRepo({"library": [{"id": "book-1", "entity": "Book", "deleted": False}]})
    service = _node_service(InMemoryEntityRepo({("library", "Book"): schema}), repo)
    calls: list[dict[str, Any]] = []

    def query(module, payload, *, actor=None):
        calls.append(copy.deepcopy(payload))
        return [{"id": "book-1", "entity": "Book"}]

    service.query = query

    service.get("library", "book-1", project="*")

    assert calls == [{"filter": {"id": "book-1", "entity": "Book"}, "project": "*"}]


@pytest.mark.parametrize("actor,read_permissions,deleted,exists,allowed", [
    (None, (True, True, True), False, True, True),
    ({"user_id": "owner"}, (False, True, True), False, True, False),
    ({"user_id": "owner"}, (True, False, False), False, True, True),
    ({"user_id": "other", "groups": ["group"]}, (True, False, True), False, True, False),
    ({"user_id": "other", "groups": ["group"]}, (False, True, False), False, True, True),
    ({"role": "admin"}, (True, True, False), False, True, False),
    ({"role": "superuser"}, (False, False, False), False, True, True),
    ({"role": "superuser"}, (True, True, True), True, True, False),
    ({"role": "superuser"}, (True, True, True), False, False, False),
])
def test_get_checks_stored_acl_before_query_hooks(actor, read_permissions, deleted, exists, allowed):
    node = {"id": "book-1", "entity": "Book", "name": "Book", "deleted": deleted,
            "owner": "owner", "group": "group", "perm": {
                subject: {"r": value} for subject, value in zip(("owner", "group", "others"), read_permissions)
            }}
    repo = InMemoryNodeRepo({"library": [node] if exists else []})
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo)
    calls = []
    service.hooks.register("before_query", lambda context: calls.append(context.query), module="library")

    if allowed:
        assert service.get("library", "book-1", project=["name"], actor=actor)["name"] == "Book"
        assert calls == [{"filter": {"id": "book-1", "entity": "Book"}, "project": ["name"]}]
    else:
        with pytest.raises(NotFoundError):
            service.get("library", "book-1", project=["name"], actor=actor)
        assert calls == []
        assert repo.last_pipeline is None


@pytest.mark.parametrize("change", ["deleted", "perm"])
def test_get_rechecks_read_access_in_final_query(change):
    repo = InMemoryNodeRepo({"library": [{"id": "book-1", "entity": "Book", "name": "Book", "deleted": False}]})
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo)

    def before_query(context):
        node = repo.by_module["library"][0]
        if change == "deleted":
            node["deleted"] = True
        else:
            node["perm"]["others"]["r"] = False

    service.hooks.register("before_query", before_query, module="library")

    with pytest.raises(NotFoundError):
        service.get("library", "book-1", project=["name"])
    assert repo.last_pipeline is not None


def test_list_entity_keeps_required_entity_at_filter_root():
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), InMemoryNodeRepo())
    calls: list[dict[str, Any]] = []

    def query(module, payload, *, actor=None):
        calls.append(copy.deepcopy(payload))
        return []

    service.query = query

    service.list_entity(
        "library",
        "Book",
        {"filter": {"or": [{"entity": "Author"}, {"name": "A"}]}, "sort": {"name": "asc"}},
    )

    assert calls == [
        {
            "filter": {
                "entity": "Book",
                "and": [{"or": [{"entity": "Author"}, {"name": "A"}]}],
            },
            "sort": {"name": "asc"},
            "project": ["*", "owner.*", "group.*"],
        }
    ]


def test_before_query_error_prevents_repository_execution():
    hooks = NodeHookRegistry()
    repo = InMemoryNodeRepo()
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo, hook_registry=hooks)
    error = QueryValidationError("Application rejected query")

    def before_query(context):
        raise error

    hooks.register("before_query", before_query, module="library")

    with pytest.raises(QueryValidationError) as caught:
        service.query("library", {"filter": {"entity": "Book"}})

    assert caught.value is error
    assert repo.last_pipeline is None


def test_after_query_can_mutate_and_replace_result_in_priority_order():
    hooks = NodeHookRegistry()
    repo = InMemoryNodeRepo({"library": [{"id": "book-1", "entity": "Book", "name": "A", "deleted": False}]})
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo, hook_registry=hooks)
    calls = []
    payload = {"filter": {"entity": "Book"}}
    actor = {"role": "superuser"}

    def enrich(context):
        calls.append((context.event, context.module, context.query, context.actor))
        context.result[0]["label"] = context.result[0]["name"]

    def replace(context):
        context.result = [{"label": row["label"]} for row in context.result]

    hooks.register("after_query", replace, module="library", priority=200)
    hooks.register("after_query", enrich, module="library", priority=100)

    result = service.query("library", payload, actor=actor)

    assert result == [{"label": "A"}]
    assert calls == [("after_query", "library", payload, actor)]
    assert "label" not in repo.find_by_id("library", "book-1")


def test_after_query_receives_empty_results_and_modified_query():
    hooks = NodeHookRegistry()
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), InMemoryNodeRepo(), hook_registry=hooks)
    calls = []
    payload = {"project": ["name"]}

    def before_query(context):
        context.query["filter"] = {"entity": "Book"}

    def after_query(context):
        calls.append((copy.deepcopy(context.query), context.result))

    hooks.register("before_query", before_query, module="library")
    hooks.register("after_query", after_query, module="library")

    assert service.query("library", payload) == []
    assert calls == [({"project": ["name"], "filter": {"entity": "Book"}}, [])]
    assert payload == {"project": ["name"]}


def test_after_query_propagates_handler_error_after_execution():
    hooks = NodeHookRegistry()
    repo = InMemoryNodeRepo()
    service = _node_service(InMemoryEntityRepo({("library", "Book"): _book_schema()}), repo, hook_registry=hooks)
    error = RuntimeError("Application could not process result")

    def after_query(context):
        raise error

    hooks.register("after_query", after_query, module="library")

    with pytest.raises(RuntimeError) as caught:
        service.query("library", {})

    assert caught.value is error
    assert repo.last_pipeline is not None
