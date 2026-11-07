from __future__ import annotations

import pytest
from pymongo.errors import DuplicateKeyError

from sandala.core.errors import DefaultGroupDeletionForbiddenError, IdentityInUseError, LastSuperuserDeletionForbiddenError
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_users_bootstrap_creates_identity_unique_indexes():
    with mongo_services(mongo_db="sandala_it_users_identity_indexes") as (_, _, node_repo):
        collection = node_repo.collection("users")
        indexes = list(collection.list_indexes())

        assert any(
            index["name"] == "sandala_user_username_unique"
            and index["key"] == {"username": 1}
            and index.get("unique") is True
            and index.get("partialFilterExpression") == {"entity": "user"}
            for index in indexes
        )
        assert any(
            index["name"] == "sandala_user_email_unique"
            and index["key"] == {"email": 1}
            and index.get("unique") is True
            and index.get("partialFilterExpression") == {
                "entity": "user",
                "email": {"$type": "string"},
            }
            for index in indexes
        )

        collection.insert_one(
            {
                "id": "10000000-0000-4000-8000-000000000000",
                "entity": "user",
                "deleted": True,
                "username": "retired-user",
                "email": "retired@example.com",
            }
        )
        with pytest.raises(DuplicateKeyError):
            collection.insert_one(
                {
                    "id": "20000000-0000-4000-8000-000000000000",
                    "entity": "user",
                    "deleted": False,
                    "username": "retired-user",
                    "email": "other@example.com",
                }
            )
        with pytest.raises(DuplicateKeyError):
            collection.insert_one(
                {
                    "id": "30000000-0000-4000-8000-000000000000",
                    "entity": "user",
                    "deleted": False,
                    "username": "another-user",
                    "email": "retired@example.com",
                }
            )
        collection.insert_one(
            {
                "id": "40000000-0000-4000-8000-000000000000",
                "entity": "user",
                "deleted": False,
                "username": "without-email-one",
                "email": None,
            }
        )
        collection.insert_one(
            {
                "id": "50000000-0000-4000-8000-000000000000",
                "entity": "user",
                "deleted": False,
                "username": "without-email-two",
                "email": None,
            }
        )


@pytest.mark.integration
def test_users_bootstrap_root_user_has_primary_group_in_groups():
    with mongo_services(mongo_db="sandala_it_users_bootstrap") as (_, _, node_repo):
        root_user = node_repo.find_one(
            "users",
            {
                "entity": "user",
                "deleted": False,
                "username": "admin",
            },
            {"_id": 0},
        )

        assert root_user is not None
        assert isinstance(root_user.get("primary_group"), str) and root_user["primary_group"]
        assert isinstance(root_user.get("groups"), list)
        assert root_user["primary_group"] in root_user["groups"]
        assert len(root_user["groups"]) >= 1


@pytest.mark.integration
def test_user_create_without_primary_group_assigns_default_group():
    with mongo_services(mongo_db="sandala_it_users_default_group") as (_, node_service, node_repo):
        default_group = node_repo.find_one(
            "users",
            {
                "entity": "group",
                "deleted": False,
                "is_default": True,
            },
            {"_id": 0},
        )
        assert default_group is not None
        root_user = node_repo.find_one(
            "users",
            {
                "entity": "user",
                "deleted": False,
                "username": "admin",
            },
            {"_id": 0},
        )
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
            },
        )

        assert created["primary_group"] == default_group["id"]
        assert created["groups"] == [default_group["id"]]


@pytest.mark.integration
def test_delete_rejects_last_active_superuser_and_referenced_group():
    with mongo_services(mongo_db="sandala_it_users_delete_references") as (_, node_service, node_repo):
        root_user = node_repo.find_one("users", {"entity": "user", "username": "admin", "deleted": False}, {"_id": 0})
        assert root_user is not None
        actor = {
            "user_id": root_user["id"],
            "role": "superuser",
            "primary_group": root_user["primary_group"],
            "groups": root_user["groups"],
        }

        with pytest.raises(LastSuperuserDeletionForbiddenError):
            node_service.delete("users", root_user["id"], actor={**actor, "user_id": "another-user"})

        group = node_service.create("users", "group", {"groupname": "team"}, actor=actor)
        node_service.create(
            "users",
            "user",
            {"username": "alice", "password": "Abcd1234!", "role": "all", "active": True, "primary_group": group["id"], "groups": [group["id"]]},
            actor=actor,
        )

        with pytest.raises(IdentityInUseError) as exc_info:
            node_service.delete("users", group["id"], actor=actor)
        assert exc_info.value.details["reference_type"] == "user.primary_group"


@pytest.mark.integration
def test_delete_allows_unreferenced_user_and_nondefault_group():
    with mongo_services(mongo_db="sandala_it_users_delete_success") as (_, node_service, node_repo):
        root_user = node_repo.find_one("users", {"entity": "user", "username": "admin", "deleted": False}, {"_id": 0})
        assert root_user is not None
        actor = {"user_id": root_user["id"], "role": "superuser", "primary_group": root_user["primary_group"], "groups": root_user["groups"]}
        user = node_service.create("users", "user", {"username": "alice", "password": "Abcd1234!", "role": "all", "active": True, "groups": []}, actor=actor)
        group = node_service.create("users", "group", {"groupname": "team"}, actor=actor)

        assert node_service.delete("users", user["id"], actor=actor) == 1
        assert node_service.delete("users", group["id"], actor=actor) == 1


@pytest.mark.integration
def test_delete_rejects_cross_module_and_module_root_identity_references():
    with mongo_services(mongo_db="sandala_it_users_delete_references_all") as (_, node_service, node_repo):
        root_user = node_repo.find_one("users", {"entity": "user", "username": "admin", "deleted": False}, {"_id": 0})
        assert root_user is not None
        actor = {"user_id": root_user["id"], "role": "superuser", "primary_group": root_user["primary_group"], "groups": root_user["groups"]}
        user = node_service.create("users", "user", {"username": "alice", "password": "Abcd1234!", "role": "all", "active": True, "groups": []}, actor=actor)
        group = node_service.create("users", "group", {"groupname": "team"}, actor=actor)
        module_repo = node_service._module_repo
        module_repo.create_module({"name": "library", "description": "library", "root_owner": root_user["id"], "root_group": root_user["primary_group"], "root_children_entities": [], "root_perm": {"owner": {"p": True}, "group": {"p": True}, "others": {"p": True}}})
        node_repo.collection("library").insert_one({"id": "doc", "entity": "Doc", "parent": None, "depth": 0, "ancestors": [], "deleted": False, "cdate": "2020-01-01T00:00:00Z", "mdate": "2020-01-01T00:00:00Z", "owner": user["id"], "group": group["id"], "perm": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": True, "w": True, "p": True}, "others": {"r": True, "w": True, "p": True}}})

        with pytest.raises(IdentityInUseError) as user_exc:
            node_service.delete("users", user["id"], actor=actor)
        assert user_exc.value.details["reference_type"] == "node.owner"
        with pytest.raises(IdentityInUseError) as group_exc:
            node_service.delete("users", group["id"], actor=actor)
        assert group_exc.value.details["reference_type"] == "node.group"

        node_repo.collection("library").delete_many({})
        module_repo.update_module("library", {"root_owner": user["id"], "root_group": group["id"]})
        with pytest.raises(IdentityInUseError) as root_user_exc:
            node_service.delete("users", user["id"], actor=actor)
        assert root_user_exc.value.details["reference_type"] == "module.root_owner"
        with pytest.raises(IdentityInUseError) as root_group_exc:
            node_service.delete("users", group["id"], actor=actor)
        assert root_group_exc.value.details["reference_type"] == "module.root_group"


@pytest.mark.integration
def test_delete_rejects_default_group():
    with mongo_services(mongo_db="sandala_it_users_delete_default_group") as (_, node_service, node_repo):
        root_user = node_repo.find_one("users", {"entity": "user", "username": "admin", "deleted": False}, {"_id": 0})
        assert root_user is not None
        actor = {"user_id": root_user["id"], "role": "superuser", "primary_group": root_user["primary_group"], "groups": root_user["groups"]}

        with pytest.raises(DefaultGroupDeletionForbiddenError):
            node_service.delete("users", root_user["primary_group"], actor=actor)
