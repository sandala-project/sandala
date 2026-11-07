from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from tests.integration.helpers import mongo_services
from tests.integration.node_patch_fixtures import bootstrap_admin_actor, node, seed_entities, seed_tree


@pytest.mark.integration
def test_acl_patch_updates_acl_fields_without_changing_other_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        before = node_repo.find_by_id("library", ids["moving"])
        new_perm = {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": False, "w": False, "p": False},
            "others": {"r": False, "w": False, "p": False},
        }

        result = node_service.patch_acl(
            "library",
            ids["moving"],
            {
                "owner": actor["user_id"],
                "group": actor["primary_group"],
                "perm": new_perm,
            },
            actor=actor,
        )

        current = node_repo.find_by_id("library", ids["moving"])
        assert result["updated_count"] == 1
        assert result["node"]["id"] == ids["moving"]
        assert current["owner"] == actor["user_id"]
        assert current["group"] == actor["primary_group"]
        assert current["perm"] == new_perm
        assert current["name"] == before["name"]
        assert current["parent"] == before["parent"]
        assert current["depth"] == before["depth"]
        assert current["ancestors"] == before["ancestors"]


@pytest.mark.integration
def test_acl_patch_recursively_bulk_updates_active_subtree_only():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        deleted_id = "50000000-0000-4500-8500-000000000006"
        deleted = node(
            deleted_id,
            "Category",
            parent=ids["grand"],
            depth=5,
            ancestors=[ids["root"], ids["branch1"], ids["moving"], ids["child"], ids["grand"]],
            name="Deleted",
            deleted=True,
        )
        node_repo.collection("library").insert_one(deleted)
        new_perm = {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": False, "w": False, "p": False},
            "others": {"r": False, "w": False, "p": False},
        }
        deleted_before = node_repo.find_by_id("library", deleted_id)

        result = node_service.patch_acl(
            "library",
            ids["moving"],
            {"perm": new_perm},
            recursive=True,
            actor=actor,
        )

        assert result["updated_count"] == 3
        for node_id in (ids["moving"], ids["child"], ids["grand"]):
            assert node_repo.find_by_id("library", node_id)["perm"] == new_perm
        assert node_repo.find_by_id("library", deleted_id) == deleted_before


@pytest.mark.integration
def test_acl_hooks_can_change_acl_fields_and_receive_persisted_result():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        new_perm = {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": False, "w": False, "p": False},
            "others": {"r": False, "w": False, "p": False},
        }
        events = []

        def before_acl_patch(context):
            events.append((context.event, context.node_id))
            context.payload["perm"] = new_perm

        def after_acl_patch(context):
            events.append((context.event, context.node_id))
            assert context.result["perm"] == new_perm
            assert set(context.payload) == {"perm", "mdate"}

        node_service.hooks.register("before_acl_patch", before_acl_patch)
        node_service.hooks.register("after_acl_patch", after_acl_patch)

        result = node_service.patch_acl(
            "library",
            ids["moving"],
            {"perm": {"owner": {"r": True, "w": True, "p": True}}},
            actor=actor,
        )

        assert result["updated_count"] == 1
        assert events == [
            ("before_acl_patch", ids["moving"]),
            ("after_acl_patch", ids["moving"]),
        ]


@pytest.mark.integration
def test_acl_hook_cannot_add_non_acl_fields_and_prevents_write():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        before = node_repo.find_by_id("library", ids["moving"])
        after_calls = []

        def before_acl_patch(context):
            context.payload["name"] = "must not be persisted"

        node_service.hooks.register("before_acl_patch", before_acl_patch)
        node_service.hooks.register("after_acl_patch", lambda context: after_calls.append(context.node_id))

        with pytest.raises(ValidationError, match="may only change owner, group and perm"):
            node_service.patch_acl(
                "library",
                ids["moving"],
                {"perm": before["perm"]},
                actor=actor,
            )

        assert node_repo.find_by_id("library", ids["moving"]) == before
        assert after_calls == []


@pytest.mark.integration
def test_acl_patch_revalidates_hook_acl_changes_for_effective_actor():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        before = node_repo.find_by_id("library", ids["moving"])
        new_perm = {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": False, "w": False, "p": False},
            "others": {"r": False, "w": False, "p": False},
        }

        def before_acl_patch(context):
            context.actor = {
                "role": "all",
                "user_id": "99999999-9999-4999-8999-999999999999",
                "groups": [before["group"]],
            }
            context.payload["perm"] = new_perm

        node_service.hooks.register("before_acl_patch", before_acl_patch)

        with pytest.raises(ValidationError, match="Field 'perm' can only be changed"):
            node_service.patch_acl(
                "library",
                ids["moving"],
                {"perm": new_perm},
                actor=actor,
            )

        assert node_repo.find_by_id("library", ids["moving"]) == before
