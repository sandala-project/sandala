from __future__ import annotations

import pytest

from sandala.core.errors import ConflictError, NodeIdAlreadyExistsError, ValidationError
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_new_module_node_collection_has_base_indexes():
    with mongo_services(mongo_db="sandala_it_node_indexes") as (entity_service, _, node_repo):
        entity_service.create("library", "Book", _book_schema())

        indexes = list(node_repo.collection("library").list_indexes())

        assert any(
            index["name"] == "sandala_id_unique" and index["key"] == {"id": 1} and index.get("unique") is True
            for index in indexes
        )
        assert any(
            index["name"] == "sandala_entity_deleted_id" and index["key"] == {"entity": 1, "deleted": 1, "_id": 1}
            for index in indexes
        )
        assert any(
            index["name"] == "sandala_parent_deleted_id" and index["key"] == {"parent": 1, "deleted": 1, "_id": 1}
            for index in indexes
        )


@pytest.mark.integration
def test_create_root_node_succeeds_when_entity_allowed_in_root():
    with mongo_services(mongo_db="sandala_it_node_create_root_allowed") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        node_service._module_repo.update_module("library", {"root_children_entities": ["Book"]})
        actor = _bootstrap_admin_actor(node_repo)

        created = node_service.create(
            "library",
            "Book",
            {"name": "War and Peace"},
            actor=actor,
        )

        stored = node_repo.find_by_id("library", created["id"], deleted=False)
        assert created["entity"] == "Book"
        assert created["parent"] is None
        assert created["depth"] == 0
        assert created["ancestors"] == []
        assert stored is not None


@pytest.mark.integration
def test_create_node_with_duplicate_id_raises_conflict_error():
    with mongo_services(mongo_db="sandala_it_node_duplicate_id") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        node_service._module_repo.update_module("library", {"root_children_entities": ["Book"]})
        actor = _bootstrap_admin_actor(node_repo)
        node_id = "50000000-0000-4500-8500-000000000000"

        node_service.create("library", "Book", {"id": node_id, "name": "First"}, actor=actor)

        with pytest.raises(NodeIdAlreadyExistsError):
            node_service.create("library", "Book", {"id": node_id, "name": "Second"}, actor=actor)


@pytest.mark.integration
def test_create_node_with_integrator_unique_index_conflict_raises_generic_conflict_error():
    with mongo_services(mongo_db="sandala_it_node_integrator_unique_index") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        node_service._module_repo.update_module("library", {"root_children_entities": ["Book"]})
        node_repo.collection("library").create_index("owner", name="integrator_owner_unique", unique=True)
        actor = _bootstrap_admin_actor(node_repo)

        node_service.create("library", "Book", {"name": "First"}, actor=actor)

        with pytest.raises(ConflictError) as exc_info:
            node_service.create("library", "Book", {"name": "Second"}, actor=actor)

        assert type(exc_info.value) is ConflictError


@pytest.mark.integration
def test_patch_node_with_integrator_unique_index_conflict_raises_generic_conflict_error():
    with mongo_services(mongo_db="sandala_it_node_patch_integrator_unique_index") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        node_service._module_repo.update_module("library", {"root_children_entities": ["Book"]})
        actor = _bootstrap_admin_actor(node_repo)
        first = node_service.create("library", "Book", {"name": "First"}, actor=actor)
        second = node_service.create("library", "Book", {"name": "Second"}, actor=actor)
        node_repo.collection("library").create_index("name", name="integrator_name_unique", unique=True)

        with pytest.raises(ConflictError) as exc_info:
            node_service.patch("library", second["id"], {"name": first["name"]}, actor=actor)

        assert type(exc_info.value) is ConflictError


@pytest.mark.integration
def test_create_root_node_fails_when_entity_not_in_root_children_entities():
    with mongo_services(mongo_db="sandala_it_node_create_root_denied") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        entity_service.create("library", "Category", _category_schema(children=[]))
        node_service._module_repo.update_module("library", {"root_children_entities": ["Category"]})
        actor = _bootstrap_admin_actor(node_repo)

        with pytest.raises(ValidationError, match="cannot be added to module root"):
            node_service.create(
                "library",
                "Book",
                {"name": "War and Peace"},
                actor=actor,
            )


@pytest.mark.integration
def test_create_child_node_succeeds_under_allowed_parent_entity():
    with mongo_services(mongo_db="sandala_it_node_create_child_allowed") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        entity_service.create("library", "Category", _category_schema(children=["Book"]))
        node_service._module_repo.update_module("library", {"root_children_entities": ["Category"]})
        actor = _bootstrap_admin_actor(node_repo)

        parent = node_service.create(
            "library",
            "Category",
            {"name": "Shelf"},
            actor=actor,
        )
        created = node_service.create(
            "library",
            "Book",
            {"name": "War and Peace", "parent": parent["id"]},
            actor=actor,
        )

        assert created["parent"] == parent["id"]
        assert created["depth"] == 1
        assert created["ancestors"] == [parent["id"]]


@pytest.mark.integration
def test_create_child_node_fails_under_disallowed_parent_entity():
    with mongo_services(mongo_db="sandala_it_node_create_child_denied") as (entity_service, node_service, node_repo):
        entity_service.create("library", "Book", _book_schema())
        entity_service.create("library", "Category", _category_schema(children=[]))
        node_service._module_repo.update_module("library", {"root_children_entities": ["Category"]})
        actor = _bootstrap_admin_actor(node_repo)

        parent = node_service.create(
            "library",
            "Category",
            {"name": "Shelf"},
            actor=actor,
        )

        with pytest.raises(ValidationError, match="cannot be added under parent entity 'Category'"):
            node_service.create(
                "library",
                "Book",
                {"name": "War and Peace", "parent": parent["id"]},
                actor=actor,
            )


@pytest.mark.integration
def test_create_users_user_applies_hooks_and_acl_defaults():
    with mongo_services(mongo_db="sandala_it_node_create_users_hooks") as (_, node_service, node_repo):
        default_group = node_repo.find_one(
            "users",
            {"entity": "group", "deleted": False, "is_default": True},
            {"_id": 0},
        )
        root_user = node_repo.find_one(
            "users",
            {"entity": "user", "deleted": False, "username": "admin"},
            {"_id": 0},
        )
        assert default_group is not None
        assert root_user is not None

        created = node_service.create(
            "users",
            "user",
            {
                "username": "alice",
                "password": "Abcd1234!",
                "role": "all",
                "active": True,
                "groups": [],
            },
            actor={
                "user_id": root_user["id"],
                "role": "superuser",
                "primary_group": root_user["primary_group"],
                "groups": [root_user["primary_group"]],
            },
        )

        stored = node_repo.find_by_id("users", created["id"], deleted=False)
        assert created["primary_group"] == default_group["id"]
        assert created["groups"] == [default_group["id"]]
        assert created["group"] == default_group["id"]
        assert "password_hash" not in created
        assert stored is not None
        assert isinstance(stored.get("password_hash"), str) and stored["password_hash"]


def _bootstrap_admin_actor(node_repo) -> dict[str, object]:
    root_user = node_repo.find_one(
        "users",
        {"entity": "user", "deleted": False, "username": "admin"},
        {"_id": 0},
    )
    assert root_user is not None
    return {
        "user_id": root_user["id"],
        "role": "superuser",
        "primary_group": root_user["primary_group"],
        "groups": root_user["groups"],
    }


def _book_schema() -> dict:
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
                    "group": {"r": False, "w": False, "p": False},
                    "others": {"r": False, "w": False, "p": False},
                }
            },
        },
    }


def _category_schema(*, children: list[str]) -> dict:
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
        "x-meta": {
            "children": {"entities": children},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": False, "w": False, "p": False},
                    "others": {"r": False, "w": False, "p": False},
                }
            },
        },
    }
