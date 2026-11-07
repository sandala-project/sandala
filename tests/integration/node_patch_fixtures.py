from __future__ import annotations


def seed_entities(entity_service) -> None:
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


def seed_book_entity(entity_service) -> None:
    entity_service.create(
        "library",
        "Book",
        {
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
                },
                "secret": {
                    "type": "string",
                    "x-meta": {
                        "semantic-type": "String",
                        "visibility-mode": "admin",
                        "write-mode": "all",
                    },
                },
            },
            "required": ["name", "secret"],
            "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
        },
    )


def seed_tree(node_repo):
    ids = {
        "root": "50000000-0000-4500-8500-000000000000",
        "branch1": "50000000-0000-4500-8500-000000000001",
        "branch2": "50000000-0000-4500-8500-000000000002",
        "moving": "50000000-0000-4500-8500-000000000003",
        "child": "50000000-0000-4500-8500-000000000004",
        "grand": "50000000-0000-4500-8500-000000000005",
    }

    docs = [
        node(ids["root"], "Category", parent=None, depth=0, ancestors=[], name="Root"),
        node(ids["branch1"], "Category", parent=ids["root"], depth=1, ancestors=[ids["root"]], name="A"),
        node(ids["branch2"], "Category", parent=ids["root"], depth=1, ancestors=[ids["root"]], name="B"),
        node(
            ids["moving"],
            "Category",
            parent=ids["branch1"],
            depth=2,
            ancestors=[ids["root"], ids["branch1"]],
            name="X",
        ),
        node(
            ids["child"],
            "Category",
            parent=ids["moving"],
            depth=3,
            ancestors=[ids["root"], ids["branch1"], ids["moving"]],
            name="Y",
        ),
        node(
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


def bootstrap_admin_actor(node_repo, *, role: str = "superuser") -> dict[str, object]:
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
    return {
        "user_id": root_user["id"],
        "primary_group": root_user["primary_group"],
        "groups": root_user.get("groups", [root_user["primary_group"]]),
        "role": role,
    }


def node(node_id: str, entity: str, parent, depth: int, ancestors: list[str], **fields):
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
