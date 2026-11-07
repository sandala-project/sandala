from __future__ import annotations

import pytest

from sandala.core.errors import DescendantWriteForbiddenError
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_delete_marks_subtree_as_deleted_only():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_entities(entity_service)
        ids = _seed_tree(node_repo)

        deleted_count = node_service.delete("library", ids["moving"])

        moving = node_repo.find_by_id("library", ids["moving"])
        child = node_repo.find_by_id("library", ids["child"])
        grand = node_repo.find_by_id("library", ids["grand"])
        branch2 = node_repo.find_by_id("library", ids["branch2"])

        assert deleted_count == 3
        assert moving["deleted"] is True
        assert child["deleted"] is True
        assert grand["deleted"] is True
        assert branch2["deleted"] is False


@pytest.mark.integration
def test_delete_rejects_subtree_when_an_active_descendant_lacks_w_permission():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_entities(entity_service)
        ids = _seed_tree(node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["child"]},
            {
                "$set": {
                    "owner": "33333333-3333-4333-8333-333333333333",
                    "perm": {
                        "owner": {"r": True, "w": True, "p": True},
                        "group": {"r": True, "w": False, "p": False},
                        "others": {"r": True, "w": False, "p": False},
                    },
                }
            },
        )

        with pytest.raises(DescendantWriteForbiddenError) as exc_info:
            node_service.delete(
                "library",
                ids["moving"],
                actor={"user_id": "11111111-1111-4111-8111-111111111111"},
            )

        assert exc_info.value.code == "descendant_write_forbidden"
        assert ids["child"] not in exc_info.value.message
        assert node_repo.find_by_id("library", ids["moving"])["deleted"] is False
        assert node_repo.find_by_id("library", ids["child"])["deleted"] is False


def _seed_entities(entity_service) -> None:
    category_schema = {
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
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }
    entity_service.create("library", "Category", category_schema)
    category_schema["x-meta"]["children"]["entities"] = ["Category"]
    entity_service.update("library", "Category", category_schema)


def _seed_tree(node_repo):
    ids = {
        "root": "80000000-0000-4800-8800-000000000000",
        "branch1": "80000000-0000-4800-8800-000000000001",
        "branch2": "80000000-0000-4800-8800-000000000002",
        "moving": "80000000-0000-4800-8800-000000000003",
        "child": "80000000-0000-4800-8800-000000000004",
        "grand": "80000000-0000-4800-8800-000000000005",
    }

    docs = [
        _node(ids["root"], "Category", parent=None, depth=0, ancestors=[], name="Root"),
        _node(ids["branch1"], "Category", parent=ids["root"], depth=1, ancestors=[ids["root"]], name="A"),
        _node(ids["branch2"], "Category", parent=ids["root"], depth=1, ancestors=[ids["root"]], name="B"),
        _node(
            ids["moving"],
            "Category",
            parent=ids["branch1"],
            depth=2,
            ancestors=[ids["root"], ids["branch1"]],
            name="X",
        ),
        _node(
            ids["child"],
            "Category",
            parent=ids["moving"],
            depth=3,
            ancestors=[ids["root"], ids["branch1"], ids["moving"]],
            name="Y",
        ),
        _node(
            ids["grand"],
            "Category",
            parent=ids["child"],
            depth=4,
            ancestors=[ids["root"], ids["branch1"], ids["moving"], ids["child"]],
            name="Z",
        ),
    ]
    node_repo.collection("library").insert_many(docs)
    return ids


def _node(node_id: str, entity: str, parent, depth: int, ancestors: list[str], **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": parent,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": True, "w": True, "p": True},
            "others": {"r": True, "w": True, "p": True},
        },
        "depth": depth,
        "ancestors": ancestors,
        "deleted": False,
        "cdate": "2020-01-01T00:00:00Z",
        "mdate": "2020-01-01T00:00:00Z",
        **fields,
    }
