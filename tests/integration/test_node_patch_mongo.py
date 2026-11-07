from __future__ import annotations

from copy import deepcopy

import pytest

from sandala.core.errors import LinkPatchAclHiddenReferencesMissingError, ValidationError
from tests.integration.helpers import mongo_services
from tests.integration.node_patch_fixtures import bootstrap_admin_actor, seed_book_entity, seed_entities, seed_tree
from tests.integration.test_node_query_object_array_mongo import (
    _node,
    _product_schema,
    _seed_object_array_dataset,
)
from tests.integration.query_dataset import book_schema, seed_query_dataset


@pytest.mark.integration
def test_patch_updates_node_fields_without_hierarchy_change():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)

        moving_before = node_repo.find_by_id("library", ids["moving"])
        child_before = node_repo.find_by_id("library", ids["child"])

        patched = node_service.patch("library", ids["moving"], {"name": "X2"})

        moving_after = node_repo.find_by_id("library", ids["moving"])
        child_after = node_repo.find_by_id("library", ids["child"])

        assert patched["name"] == "X2"
        assert moving_after["name"] == "X2"
        assert moving_after["parent"] == moving_before["parent"]
        assert moving_after["depth"] == moving_before["depth"]
        assert moving_after["ancestors"] == moving_before["ancestors"]
        assert moving_after["cdate"] == moving_before["cdate"]
        assert moving_after["mdate"] != moving_before["mdate"]
        assert child_after["ancestors"] == child_before["ancestors"]
        assert child_after["depth"] == child_before["depth"]


@pytest.mark.integration
def test_patch_linkarray_preserves_only_acl_hidden_targets_for_original_actor():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        actor = {"role": "all"}
        node_repo.collection("library").update_one(
            {"id": ids["author_boris"]},
            {"$set": {"perm.others.r": False}},
        )
        node_repo.collection("library").update_one(
            {"id": ids["magazine_1"]},
            {"$set": {"perm.others.r": False}},
        )
        node_repo.collection("library").update_one(
            {"id": ids["book_alpha"]},
            {"$push": {"editors": ids["magazine_1"]}},
        )

        resolved = node_service.get("library", ids["book_alpha"], actor=actor)
        assert [editor["id"] for editor in resolved["editors"]] == [ids["author_anna"]]

        node_service.patch(
            "library",
            ids["book_alpha"],
            {"editors": [ids["author_clara"]]},
            actor=actor,
        )

        stored = node_repo.find_by_id("library", ids["book_alpha"])
        assert stored is not None
        assert stored["editors"] == [
            ids["author_clara"],
            ids["author_boris"],
        ]


@pytest.mark.integration
def test_patch_linkarray_is_completed_before_before_patch_even_if_hook_changes_actor():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        actor = {"role": "all"}
        node_repo.collection("library").update_one(
            {"id": ids["author_boris"]},
            {"$set": {"perm.others.r": False}},
        )
        seen_payloads = []

        def before_patch(context):
            seen_payloads.append(context.payload["editors"])
            context.actor = {"role": "superuser"}

        node_service.hooks.register("before_patch", before_patch, module="library", entity="Book")
        node_service.patch(
            "library",
            ids["book_alpha"],
            {"editors": [ids["author_clara"]]},
            actor=actor,
        )

        assert seen_payloads == [[
            ids["author_clara"],
            ids["author_boris"],
        ]]


@pytest.mark.integration
def test_patch_linkarray_drops_deleted_and_disallowed_targets_for_superuser():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["book_alpha"]},
            {"$push": {"editors": ids["magazine_1"]}},
        )

        node_service.patch(
            "library",
            ids["book_alpha"],
            {"editors": [ids["author_clara"]]},
            actor={"role": "superuser"},
        )

        stored = node_repo.find_by_id("library", ids["book_alpha"])
        assert stored is not None
        assert stored["editors"] == [ids["author_clara"]]


@pytest.mark.integration
def test_patch_rejects_null_for_nullable_linkarray_with_acl_hidden_reference():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        schema = book_schema()
        schema["properties"]["editors"] = {
            "anyOf": [
                schema["properties"]["editors"],
                {"type": "null"},
            ]
        }
        entity_service.update("library", "Book", schema)
        node_repo.collection("library").update_one(
            {"id": ids["author_boris"]},
            {"$set": {"perm.others.r": False}},
        )

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                ids["book_alpha"],
                {"editors": None},
                actor={"role": "all"},
            )

        assert exc_info.value.details["field_errors"][0]["location"] == ["editors"]


@pytest.mark.integration
def test_patch_rejects_change_to_acl_hidden_single_link():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["company_a"]},
            {"$set": {"perm.others.r": False}},
        )
        node_repo.collection("library").update_one(
            {"id": ids["product_alpha"]},
            {
                "$set": {
                    "owner": "11111111-1111-4111-8111-111111111111",
                    "group": "22222222-2222-4222-8222-222222222222",
                }
            },
        )
        product = node_repo.find_by_id("library", ids["product_alpha"])
        assert product is not None
        payload_meta = deepcopy(product["meta"])
        del payload_meta["manufacturer"]

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                ids["product_alpha"],
                {"meta": payload_meta},
                actor={"role": "all"},
            )

        assert exc_info.value.details == {
            "field_errors": [
                {
                    "location": ["meta", "manufacturer"],
                    "message": "Value must retain ACL-hidden references",
                    "keyword": "acl_hidden_references",
                }
            ]
        }

        node_service.patch(
            "library",
            ids["product_alpha"],
            {"meta": deepcopy(product["meta"])},
            actor={"role": "all"},
        )


@pytest.mark.integration
def test_patch_rejects_change_to_acl_hidden_single_link_under_array():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["person_anna"]},
            {"$set": {"perm.others.r": False}},
        )
        product = node_repo.find_by_id("library", ids["product_alpha"])
        assert product is not None
        payload_variants = deepcopy(product["variants"])
        payload_variants[0]["inspector"] = ids["person_boris"]

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                ids["product_alpha"],
                {"variants": payload_variants},
                actor={"role": "all"},
            )

        assert exc_info.value.details["field_errors"][0]["location"] == ["variants"]


@pytest.mark.integration
def test_patch_rejects_root_move_when_current_parent_is_acl_hidden():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["branch1"]},
            {"$set": {"perm.others.r": False}},
        )

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                ids["moving"],
                {"parent": None},
                actor={"role": "all"},
            )

        assert exc_info.value.details["field_errors"][0]["location"] == ["parent"]


@pytest.mark.integration
def test_patch_requires_acl_hidden_linkarray_references_under_array_in_payload():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["person_boris"]},
            {"$set": {"perm.others.r": False}},
        )
        node_repo.collection("library").update_one(
            {"id": ids["product_alpha"]},
            {
                "$set": {
                    "owner": "11111111-1111-4111-8111-111111111111",
                    "group": "22222222-2222-4222-8222-222222222222",
                }
            },
        )
        product = node_repo.find_by_id("library", ids["product_alpha"])
        assert product is not None
        payload_variants = deepcopy(product["variants"])
        payload_variants[0]["backup_inspectors"] = []
        hook_calls = []
        node_service.hooks.register("before_patch", lambda context: hook_calls.append(context.node_id))

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                ids["product_alpha"],
                {"variants": payload_variants},
                actor={"role": "all"},
            )

        assert exc_info.value.code == "link_patch_acl_hidden_references_missing"
        assert exc_info.value.details == {
            "field_errors": [
                {
                    "location": ["variants"],
                    "message": "Value must retain ACL-hidden references",
                    "keyword": "acl_hidden_references",
                }
            ]
        }
        assert hook_calls == []

        node_service.patch(
            "library",
            ids["product_alpha"],
            {"variants": product["variants"]},
            actor={"role": "all"},
        )
        assert hook_calls == [ids["product_alpha"]]
        stored = node_repo.find_by_id("library", ids["product_alpha"])
        assert stored is not None
        assert stored["variants"][0]["backup_inspectors"] == [ids["person_boris"], ids["person_deleted"]]


@pytest.mark.integration
def test_patch_allows_linkarray_under_array_when_current_branch_is_fully_resolvable():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["product_beta"]},
            {
                "$set": {
                    "owner": "11111111-1111-4111-8111-111111111111",
                    "group": "22222222-2222-4222-8222-222222222222",
                }
            },
        )
        product = node_repo.find_by_id("library", ids["product_beta"])
        assert product is not None
        variants = product["variants"]
        variants[0]["price"] = 16.0

        node_service.patch(
            "library",
            ids["product_beta"],
            {"variants": variants},
            actor={"role": "all"},
        )

        stored = node_repo.find_by_id("library", ids["product_beta"])
        assert stored is not None
        assert stored["variants"][0]["price"] == 16.0


@pytest.mark.integration
def test_patch_requires_acl_hidden_linkarray_references_under_two_nested_arrays():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_object_array_dataset(entity_service, node_repo)
        schema = _product_schema()
        variant_schema = schema["properties"]["variants"]["items"]
        variant_schema["properties"]["review"] = {
            "type": "object",
            "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            "properties": {
                "groups": {
                    "type": "array",
                    "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                        "properties": {
                            "reviewers": {
                                "type": "array",
                                "items": {"type": "string", "format": "uuid"},
                                "x-meta": {
                                    "semantic-type": "LinkArray",
                                    "visibility-mode": "all",
                                    "write-mode": "all",
                                    "link": {"module": "library", "entities": ["Person"]},
                                },
                            }
                        },
                        "required": ["reviewers"],
                    },
                }
            },
            "required": ["groups"],
        }
        variant_schema["required"].append("review")
        entity_service.create("library", "NestedProduct", schema)

        nested_product_id = "93000000-0000-4930-8930-000000001004"
        node_repo.collection("library").insert_one(
            _node(
                nested_product_id,
                "NestedProduct",
                "2026-01-01T00:00:00Z",
                owner="11111111-1111-4111-8111-111111111111",
                group="22222222-2222-4222-8222-222222222222",
                name="Nested Product",
                sku="nested",
                meta={
                    "category": "Books",
                    "stats": {"score": 80, "rank": 4},
                    "manufacturer": ids["company_a"],
                },
                variants=[
                    {
                        "code": "N-1",
                        "price": 10.0,
                        "inspector": ids["person_anna"],
                        "backup_inspectors": [ids["person_anna"]],
                        "details": {"approver": ids["person_anna"]},
                        "attributes": {"color": "red", "size": 42},
                        "review": {
                            "groups": [
                                {"reviewers": [ids["person_boris"]]},
                                {"reviewers": [ids["person_anna"]]},
                            ]
                        },
                    }
                ],
            )
        )
        node_repo.collection("library").update_one(
            {"id": ids["person_boris"]},
            {"$set": {"perm.others.r": False}},
        )

        product = node_repo.find_by_id("library", nested_product_id)
        assert product is not None
        payload_variants = deepcopy(product["variants"])
        payload_variants[0]["review"]["groups"][0]["reviewers"] = []

        with pytest.raises(LinkPatchAclHiddenReferencesMissingError) as exc_info:
            node_service.patch(
                "library",
                nested_product_id,
                {"variants": payload_variants},
                actor={"role": "all"},
            )

        assert exc_info.value.details["field_errors"][0]["location"] == ["variants"]

        payload_variants = deepcopy(product["variants"])
        payload_variants[0]["price"] = 11.0
        node_service.patch(
            "library",
            nested_product_id,
            {"variants": payload_variants},
            actor={"role": "all"},
        )
        stored = node_repo.find_by_id("library", nested_product_id)
        assert stored is not None
        assert stored["variants"][0]["price"] == 11.0


@pytest.mark.integration
def test_patch_rejects_changed_acl_fields_before_before_patch_hook():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        before = node_repo.find_by_id("library", ids["moving"])
        hook_calls = []

        node_service.hooks.register("before_patch", lambda context: hook_calls.append(context.node_id))

        changed_fields = {
            "owner": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "group": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "perm": {
                "owner": {"r": True, "w": True, "p": True},
                "group": {"r": False, "w": False, "p": False},
                "others": {"r": False, "w": False, "p": False},
            },
        }
        for field, value in changed_fields.items():
            with pytest.raises(ValidationError, match="ACL fields must be changed through"):
                node_service.patch("library", ids["moving"], {field: value}, actor=actor)

        assert hook_calls == []
        assert node_repo.find_by_id("library", ids["moving"]) == before


@pytest.mark.integration
def test_before_patch_hook_can_change_acl_fields_with_final_acl_validation():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        actor = bootstrap_admin_actor(node_repo)
        new_perm = {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": False, "w": False, "p": False},
            "others": {"r": False, "w": False, "p": False},
        }

        def before_patch(context):
            context.payload["perm"] = new_perm

        node_service.hooks.register("before_patch", before_patch)

        patched = node_service.patch(
            "library",
            ids["moving"],
            {"name": "X2"},
            actor=actor,
        )

        stored = node_repo.find_by_id("library", ids["moving"])
        assert patched["name"] == "X2"
        assert stored["name"] == "X2"
        assert stored["perm"] == new_perm


@pytest.mark.integration
def test_patch_move_to_root_rewrites_descendant_hierarchy():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)

        node_service.patch("library", ids["moving"], {"parent": None})

        moving = node_repo.find_by_id("library", ids["moving"])
        child = node_repo.find_by_id("library", ids["child"])
        grand = node_repo.find_by_id("library", ids["grand"])

        assert moving["parent"] is None
        assert moving["depth"] == 0
        assert moving["ancestors"] == []
        assert child["parent"] == ids["moving"]
        assert child["depth"] == 1
        assert child["ancestors"] == [ids["moving"]]
        assert grand["parent"] == ids["child"]
        assert grand["depth"] == 2
        assert grand["ancestors"] == [ids["moving"], ids["child"]]


@pytest.mark.integration
def test_patch_move_to_root_succeeds_when_entity_allowed_in_root_children_entities():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        node_service._module_repo.update_module("library", {"root_children_entities": ["Category"]})

        node_service.patch("library", ids["moving"], {"parent": None})

        moving = node_repo.find_by_id("library", ids["moving"])
        assert moving["parent"] is None
        assert moving["depth"] == 0
        assert moving["ancestors"] == []


@pytest.mark.integration
def test_patch_move_to_root_fails_when_entity_not_in_root_children_entities():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)
        moving_before = node_repo.find_by_id("library", ids["moving"])
        child_before = node_repo.find_by_id("library", ids["child"])
        node_service._module_repo.update_module("library", {"root_children_entities": ["Book"]})

        with pytest.raises(ValidationError, match="cannot be added to module root"):
            node_service.patch("library", ids["moving"], {"parent": None})

        moving_after = node_repo.find_by_id("library", ids["moving"])
        child_after = node_repo.find_by_id("library", ids["child"])
        assert moving_after == moving_before
        assert child_after == child_before


@pytest.mark.integration
def test_patch_move_under_another_branch_rewrites_subtree_prefix():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)

        node_service.patch("library", ids["moving"], {"parent": ids["branch2"]})

        moving = node_repo.find_by_id("library", ids["moving"])
        child = node_repo.find_by_id("library", ids["child"])
        grand = node_repo.find_by_id("library", ids["grand"])

        assert moving["parent"] == ids["branch2"]
        assert moving["depth"] == 2
        assert moving["ancestors"] == [ids["root"], ids["branch2"]]
        assert child["depth"] == 3
        assert child["ancestors"] == [ids["root"], ids["branch2"], ids["moving"]]
        assert grand["depth"] == 4
        assert grand["ancestors"] == [ids["root"], ids["branch2"], ids["moving"], ids["child"]]


@pytest.mark.integration
def test_patch_move_rejects_cycle_and_keeps_documents_unchanged():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_entities(entity_service)
        ids = seed_tree(node_repo)

        moving_before = node_repo.find_by_id("library", ids["moving"])
        child_before = node_repo.find_by_id("library", ids["child"])

        with pytest.raises(ValidationError, match="cannot be a descendant"):
            node_service.patch("library", ids["moving"], {"parent": ids["child"]})

        moving_after = node_repo.find_by_id("library", ids["moving"])
        child_after = node_repo.find_by_id("library", ids["child"])

        assert moving_after == moving_before
        assert child_after == child_before


@pytest.mark.integration
def test_create_response_applies_visibility_mode():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_book_entity(entity_service)
        all_actor = bootstrap_admin_actor(node_repo, role="all")
        admin_actor = bootstrap_admin_actor(node_repo, role="admin")

        node_all = node_service.create(
            "library",
            "Book",
            {"name": "War and Peace", "secret": "hidden"},
            actor=all_actor,
        )
        node_admin = node_service.create(
            "library",
            "Book",
            {"name": "Anna Karenina", "secret": "visible"},
            actor=admin_actor,
        )

        assert "secret" not in node_all
        assert node_all["name"] == "War and Peace"
        assert node_admin["secret"] == "visible"

        stored_all = node_repo.find_by_id("library", node_all["id"], deleted=False)
        assert stored_all is not None
        assert stored_all["secret"] == "hidden"


@pytest.mark.integration
def test_patch_response_applies_visibility_mode():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_book_entity(entity_service)
        all_actor = bootstrap_admin_actor(node_repo, role="all")
        admin_actor = bootstrap_admin_actor(node_repo, role="admin")
        created = node_service.create(
            "library",
            "Book",
            {"name": "Old", "secret": "start"},
            actor=all_actor,
        )

        patched_all = node_service.patch(
            "library", created["id"], {"name": "New", "secret": "new-secret"},
            actor=all_actor,
        )
        patched_admin = node_service.patch(
            "library", created["id"], {"secret": "admin-secret"},
            actor=admin_actor,
        )

        assert "secret" not in patched_all
        assert patched_all["name"] == "New"
        assert patched_admin["secret"] == "admin-secret"

        stored = node_repo.find_by_id("library", created["id"], deleted=False)
        assert stored is not None
        assert stored["secret"] == "admin-secret"
