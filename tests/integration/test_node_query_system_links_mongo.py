from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_parent_and_ancestors_resolve_with_real_mongo():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Author A"),
                _node("book-1", "Book", now, parent="author-1", ancestors=["author-1"], depth=1, name="Book A"),
                _node(
                    "chapter-1",
                    "Chapter",
                    now,
                    parent="book-1",
                    ancestors=["author-1", "book-1"],
                    depth=2,
                    name="Chapter A",
                ),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "parent.name", "ancestors.name"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Chapter A"
        assert row["parent"]["name"] == "Book A"
        assert sorted(item["name"] for item in row["ancestors"]) == ["Author A", "Book A"]


@pytest.mark.integration
def test_parent_visibility_is_enforced_like_link():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("book-1", "Book", now, name="Book A", internal_code="SECRET"),
                _node("chapter-1", "Chapter", now, parent="book-1", ancestors=["book-1"], depth=1, name="Chapter A"),
            ]
        )

        with pytest.raises(ValidationError, match="parent.internal_code"):
            node_service.query(
                "library",
                {
                    "project": ["name", "parent.internal_code"],
                    "filter": {"entity": "Chapter", "id": "chapter-1"},
                },
            )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "parent.internal_code"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
            actor={"role": "admin"},
        )
        assert len(rows) == 1
        assert rows[0]["parent"]["internal_code"] == "SECRET"


@pytest.mark.integration
def test_parent_nested_collision_is_detected_like_link():
    with mongo_services() as (entity_service, node_service, node_repo):
        entity_service.create("library", "Author", _author_schema())
        entity_service.create("library", "Book", _book_schema_with_author_link())
        entity_service.create("library", "Magazine", _magazine_schema_with_author_scalar())
        entity_service.create("library", "Child", _child_schema())

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Anna"),
                _node("book-1", "Book", now, name="Book A", author="author-1"),
                _node("mag-1", "Magazine", now, name="Magazine A", author="Raw Name"),
                _node("child-1", "Child", now, parent="book-1", ancestors=["book-1"], depth=1, name="Child A"),
                _node("child-2", "Child", now, parent="mag-1", ancestors=["mag-1"], depth=1, name="Child B"),
            ]
        )

        with pytest.raises(ValidationError, match="parent.author"):
            node_service.query(
                "library",
                {
                    "project": ["name", "parent.author.name"],
                    "filter": {"entity": "Child"},
                },
            )


@pytest.mark.integration
def test_ancestors_nested_collision_is_detected_like_link():
    with mongo_services() as (entity_service, node_service, node_repo):
        entity_service.create("library", "Author", _author_schema())
        entity_service.create("library", "Book", _book_schema_with_author_link())
        entity_service.create("library", "Magazine", _magazine_schema_with_author_scalar())
        entity_service.create("library", "Child", _child_schema())

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Anna"),
                _node("book-1", "Book", now, name="Book A", author="author-1"),
                _node("mag-1", "Magazine", now, name="Magazine A", author="Raw Name"),
                _node("child-1", "Child", now, parent="book-1", ancestors=["book-1"], depth=1, name="Child A"),
                _node("child-2", "Child", now, parent="mag-1", ancestors=["mag-1"], depth=1, name="Child B"),
            ]
        )

        with pytest.raises(ValidationError, match="ancestors.author"):
            node_service.query(
                "library",
                {
                    "project": ["name", "ancestors.author.name"],
                    "filter": {"entity": "Child"},
                },
            )


@pytest.mark.integration
def test_parent_array_traversal_with_nested_link_works_like_link():
    with mongo_services() as (entity_service, node_service, node_repo):
        entity_service.create("library", "Author", _author_schema())
        entity_service.create("library", "Book", _book_schema_with_variants())
        entity_service.create("library", "Child", _child_schema())

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Anna"),
                _node("author-2", "Author", now, name="Boris"),
                _node(
                    "book-1",
                    "Book",
                    now,
                    name="Book A",
                    variants=[
                        {"label": "v1", "inspector": "author-1"},
                        {"label": "v2", "inspector": "author-2"},
                    ],
                ),
                _node("child-1", "Child", now, parent="book-1", ancestors=["book-1"], depth=1, name="Child A"),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "parent.variants.inspector.name"],
                "filter": {"entity": "Child", "id": "child-1"},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Child A"
        inspectors = sorted(item["inspector"]["name"] for item in row["parent"]["variants"])
        assert inspectors == ["Anna", "Boris"]


@pytest.mark.integration
def test_ancestors_filter_and_sort_trigger_lookup_without_projection_leak():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Author A"),
                _node("book-1", "Book", now, parent="author-1", ancestors=["author-1"], depth=1, name="Book A"),
                _node("book-2", "Book", now, parent="author-1", ancestors=["author-1"], depth=1, name="Book B"),
                _node("chapter-1", "Chapter", now, parent="book-1", ancestors=["author-1", "book-1"], depth=2, name="C1"),
                _node("chapter-2", "Chapter", now, parent="book-2", ancestors=["author-1", "book-2"], depth=2, name="C2"),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name"],
                "filter": {"entity": "Chapter", "ancestors.name": "Book A"},
                "sort": {"ancestors.name": "asc"},
            },
        )

    assert [row["name"] for row in rows] == ["C1"]
    assert all("ancestors" not in row for row in rows)


@pytest.mark.integration
def test_ancestors_wildcard_hides_admin_only_for_all_and_keeps_for_admin():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("author-1", "Author", now, name="Author A"),
                _node(
                    "book-1",
                    "Book",
                    now,
                    parent="author-1",
                    ancestors=["author-1"],
                    depth=1,
                    name="Book A",
                    internal_code="SECRET-BOOK",
                ),
                _node(
                    "chapter-1",
                    "Chapter",
                    now,
                    parent="book-1",
                    ancestors=["author-1", "book-1"],
                    depth=2,
                    name="Chapter A",
                ),
            ]
        )

        rows_all = node_service.query(
            "library",
            {
                "project": ["name", "ancestors.*"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
        )
        assert len(rows_all) == 1
        assert all("internal_code" not in ancestor for ancestor in rows_all[0]["ancestors"])

        rows_admin = node_service.query(
            "library",
            {
                "project": ["name", "ancestors.*"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
            actor={"role": "admin"},
        )
        assert len(rows_admin) == 1
        book_ancestor = next(item for item in rows_admin[0]["ancestors"] if item["entity"] == "Book")
        assert book_ancestor["internal_code"] == "SECRET-BOOK"


@pytest.mark.integration
def test_owner_and_group_resolve_with_visibility_rules_like_links():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)
        root_user, default_group = _bootstrap_principals(node_repo)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node(
                    "book-1",
                    "Book",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    name="Book A",
                ),
                _node(
                    "chapter-1",
                    "Chapter",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    parent="book-1",
                    ancestors=["book-1"],
                    depth=1,
                    name="Chapter A",
                ),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "owner.username", "group.groupname"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
        )
        assert len(rows) == 1
        assert rows[0]["owner"]["username"] == "admin"
        assert rows[0]["group"]["groupname"] == "default"

        with pytest.raises(ValidationError, match="owner.email"):
            node_service.query(
                "library",
                {
                    "project": ["name", "owner.email"],
                    "filter": {"entity": "Chapter", "id": "chapter-1"},
                },
            )
        with pytest.raises(ValidationError, match="group.is_default"):
            node_service.query(
                "library",
                {
                    "project": ["name", "group.is_default"],
                    "filter": {"entity": "Chapter", "id": "chapter-1"},
                },
            )

        rows_admin = node_service.query(
            "library",
            {
                "project": ["name", "owner.email", "group.is_default"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
            actor={"role": "admin"},
        )
        assert len(rows_admin) == 1
        assert rows_admin[0]["owner"]["email"] is None
        assert rows_admin[0]["group"]["is_default"] is True


@pytest.mark.integration
def test_owner_and_group_filter_sort_trigger_lookup_without_projection_leak():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)
        root_user, default_group = _bootstrap_principals(node_repo)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node("book-1", "Book", now, owner=root_user["id"], group=default_group["id"], name="Book A"),
                _node("book-2", "Book", now, owner=root_user["id"], group=default_group["id"], name="Book B"),
                _node(
                    "chapter-1",
                    "Chapter",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    parent="book-1",
                    ancestors=["book-1"],
                    depth=1,
                    name="C1",
                ),
                _node(
                    "chapter-2",
                    "Chapter",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    parent="book-2",
                    ancestors=["book-2"],
                    depth=1,
                    name="C2",
                ),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name"],
                "filter": {"entity": "Chapter", "owner.username": "admin"},
                "sort": {"group.groupname": "asc"},
            },
            actor={"role": "admin"},
        )
        assert [row["name"] for row in rows] == ["C1", "C2"]
        assert all("owner" not in row and "group" not in row for row in rows)


@pytest.mark.integration
def test_owner_and_group_wildcard_hides_admin_only_for_all_and_keeps_for_admin():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_parent_ancestors_entities(entity_service)
        root_user, default_group = _bootstrap_principals(node_repo)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node(
                    "chapter-1",
                    "Chapter",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    name="Chapter A",
                ),
            ]
        )

        rows_all = node_service.query(
            "library",
            {
                "project": ["name", "owner.*", "group.*"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
        )
        assert len(rows_all) == 1
        assert rows_all[0]["owner"]["username"] == "admin"
        assert "email" not in rows_all[0]["owner"]
        assert rows_all[0]["group"]["groupname"] == "default"
        assert "is_default" not in rows_all[0]["group"]

        rows_admin = node_service.query(
            "library",
            {
                "project": ["name", "owner.*", "group.*"],
                "filter": {"entity": "Chapter", "id": "chapter-1"},
            },
            actor={"role": "admin"},
        )
        assert len(rows_admin) == 1
        assert rows_admin[0]["owner"]["email"] is None
        assert rows_admin[0]["group"]["is_default"] is True


@pytest.mark.integration
def test_parent_variants_with_owner_group_traversal_work_like_links():
    with mongo_services() as (entity_service, node_service, node_repo):
        entity_service.create("library", "Author", _author_schema())
        entity_service.create("library", "Book", _book_schema_with_variants())
        entity_service.create("library", "Child", _child_schema())
        root_user, default_group = _bootstrap_principals(node_repo)

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node(
                    "author-1",
                    "Author",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    name="Anna",
                ),
                _node(
                    "author-2",
                    "Author",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    name="Boris",
                ),
                _node(
                    "book-1",
                    "Book",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    name="Book A",
                    variants=[
                        {"label": "v1", "inspector": "author-1"},
                        {"label": "v2", "inspector": "author-2"},
                    ],
                ),
                _node(
                    "child-1",
                    "Child",
                    now,
                    owner=root_user["id"],
                    group=default_group["id"],
                    parent="book-1",
                    ancestors=["book-1"],
                    depth=1,
                    name="Child A",
                ),
            ]
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "parent.variants.inspector.owner.username", "parent.variants.inspector.group.groupname"],
                "filter": {"entity": "Child", "id": "child-1"},
            },
            actor={"role": "admin"},
        )

        assert len(rows) == 1
        inspectors = rows[0]["parent"]["variants"]
        assert sorted(item["inspector"]["owner"]["username"] for item in inspectors) == ["admin", "admin"]
        assert sorted(item["inspector"]["group"]["groupname"] for item in inspectors) == ["default", "default"]

def _seed_parent_ancestors_entities(entity_service) -> None:
    entity_service.create("library", "Author", _author_schema())
    entity_service.create("library", "Book", _book_schema_base())
    entity_service.create("library", "Chapter", _child_schema(title="Chapter"))


def _author_schema() -> dict:
    return {
        "title": "Author",
        "description": "Author",
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


def _book_schema_base() -> dict:
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
            "internal_code": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
            },
        },
        "required": ["name"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _book_schema_with_author_link() -> dict:
    schema = _book_schema_base()
    schema["properties"]["author"] = {
        "type": "string",
        "format": "uuid",
        "x-meta": {
            "semantic-type": "Link",
            "visibility-mode": "all",
            "write-mode": "all",
            "link": {"module": "library", "entities": ["Author"]},
        },
    }
    schema["required"].append("author")
    return schema


def _book_schema_with_variants() -> dict:
    schema = _book_schema_base()
    schema["properties"]["variants"] = {
        "type": "array",
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        "items": {
            "type": "object",
            "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            "properties": {
                "label": {
                    "type": "string",
                    "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
                },
                "inspector": {
                    "type": "string",
                    "format": "uuid",
                    "x-meta": {
                        "semantic-type": "Link",
                        "visibility-mode": "all",
                        "write-mode": "all",
                        "link": {"module": "library", "entities": ["Author"]},
                    },
                },
            },
            "required": ["label", "inspector"],
        },
    }
    schema["required"].append("variants")
    return schema


def _magazine_schema_with_author_scalar() -> dict:
    return {
        "title": "Magazine",
        "description": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
            "author": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
        },
        "required": ["name", "author"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _child_schema(title: str = "Child") -> dict:
    return {
        "title": title,
        "description": title,
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


def _node(
    node_id: str,
    entity: str,
    now: str,
    *,
    parent: str | None = None,
    ancestors: list[str] | None = None,
    depth: int = 0,
    deleted: bool = False,
    **fields,
):
    return {
        "id": node_id,
        "entity": entity,
        "parent": parent,
        "owner": "owner-default",
        "group": "group-default",
        "perm": {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": True, "w": True, "p": True},
            "others": {"r": True, "w": True, "p": True},
        },
        "depth": depth,
        "ancestors": ancestors or [],
        "deleted": deleted,
        "cdate": now,
        "mdate": now,
        **fields,
    }


def _bootstrap_principals(node_repo) -> tuple[dict, dict]:
    root_user = node_repo.find_one(
        "users",
        {"entity": "user", "deleted": False, "username": "admin"},
        {"_id": 0},
    )
    default_group = node_repo.find_one(
        "users",
        {"entity": "group", "deleted": False, "is_default": True},
        {"_id": 0},
    )
    assert root_user is not None
    assert default_group is not None
    return root_user, default_group
