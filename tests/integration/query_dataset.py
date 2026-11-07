from __future__ import annotations

from sandala.core.time_utils import utc_now_iso


def seed_query_dataset(entity_service, node_repo, *, include_magazine: bool = True) -> dict[str, str]:
    entity_service.create("library", "City", city_schema())
    entity_service.create("library", "Author", author_schema())
    entity_service.create("library", "Book", book_schema())
    if include_magazine:
        entity_service.create("library", "Magazine", magazine_schema())

    now = utc_now_iso()
    ids = {
        "city_moscow": "90000000-0000-4900-8900-000000000001",
        "city_tula": "90000000-0000-4900-8900-000000000002",
        "city_kazan": "90000000-0000-4900-8900-000000000003",
        "author_anna": "90000000-0000-4900-8900-000000000101",
        "author_boris": "90000000-0000-4900-8900-000000000102",
        "author_clara": "90000000-0000-4900-8900-000000000103",
        "author_deleted": "90000000-0000-4900-8900-000000000104",
        "author_missing": "90000000-0000-4900-8900-000000000199",
        "book_alpha": "90000000-0000-4900-8900-000000001001",
        "book_beta": "90000000-0000-4900-8900-000000001002",
        "book_gamma": "90000000-0000-4900-8900-000000001003",
        "book_delta": "90000000-0000-4900-8900-000000001004",
        "book_deleted": "90000000-0000-4900-8900-000000001005",
        "magazine_1": "90000000-0000-4900-8900-000000002001",
    }

    docs = [
        node(ids["city_moscow"], "City", now, name="Moscow", zip=101000),
        node(ids["city_tula"], "City", now, name="Tula", zip=300000),
        node(ids["city_kazan"], "City", now, name="Kazan", zip=420000),
        node(ids["author_anna"], "Author", now, name="Anna", age=34, city=ids["city_moscow"], pen_name="A.A."),
        node(ids["author_boris"], "Author", now, name="Boris", age=41, city=ids["city_tula"]),
        node(ids["author_clara"], "Author", now, name="Clara", age=29, city=ids["city_kazan"], pen_name=None),
        node(
            ids["author_deleted"],
            "Author",
            now,
            deleted=True,
            name="Ghost",
            age=99,
            city=ids["city_moscow"],
        ),
        node(
            ids["book_alpha"],
            "Book",
            now,
            name="Book Alpha",
            slug="alpha",
            pages=100,
            rating=4.7,
            subtitle="First",
            author=ids["author_anna"],
            editors=[ids["author_anna"], ids["author_boris"], ids["author_deleted"], ids["author_missing"]],
        ),
        node(
            ids["book_beta"],
            "Book",
            now,
            name="Book Beta",
            slug="beta",
            pages=220,
            rating=3.9,
            subtitle=None,
            author=ids["author_boris"],
            editors=[ids["author_boris"]],
        ),
        node(
            ids["book_gamma"],
            "Book",
            now,
            name="Book Gamma",
            slug="gamma",
            pages=150,
            rating=4.2,
            author=ids["author_clara"],
            editors=[ids["author_clara"], ids["author_anna"]],
        ),
        node(
            ids["book_delta"],
            "Book",
            now,
            name="Book Delta",
            slug="delta",
            pages=150,
            rating=4.2,
            subtitle="Tie",
            author=ids["author_anna"],
            editors=[],
        ),
        node(
            ids["book_deleted"],
            "Book",
            now,
            deleted=True,
            name="Book Deleted",
            slug="deleted",
            pages=999,
            rating=1.0,
            author=ids["author_anna"],
            editors=[ids["author_anna"]],
        ),
    ]
    if include_magazine:
        docs.append(node(ids["magazine_1"], "Magazine", now, name="Tech Monthly", author="Internal Team"))

    node_repo.collection("library").insert_many(docs)
    return ids


def city_schema() -> dict:
    return {
        "title": "City",
        "description": "City",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "zip": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "zip"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def author_schema(city_entities: list[str] | None = None) -> dict:
    allowed_city_entities = city_entities if city_entities is not None else ["City"]
    return {
        "title": "Author",
        "description": "Author",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "age": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
            "pen_name": {
                "anyOf": [
                    {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                    {"type": "null"},
                ]
            },
            "city": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": allowed_city_entities},
                },
            },
        },
        "required": ["name", "age", "city"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def book_schema(editor_entities: list[str] | None = None) -> dict:
    allowed_editor_entities = editor_entities if editor_entities is not None else ["Author"]
    return {
        "title": "Book",
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "slug": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "pages": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
            "rating": {"type": "number", "x-meta": {"semantic-type": "Number", "visibility-mode": "all", "write-mode": "all"}},
            "subtitle": {
                "anyOf": [
                    {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                    {"type": "null"},
                ]
            },
            "author": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Author"]},
                },
            },
            "editors": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "x-meta": {
                    "semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": allowed_editor_entities},
                },
            },
        },
        "required": ["name", "slug", "pages", "rating", "author", "editors"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def magazine_schema() -> dict:
    return {
        "title": "Magazine",
        "description": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "author"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def node(node_id: str, entity: str, now: str, deleted: bool = False, **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": "11111111-1111-4111-8111-111111111111",
        "group": "22222222-2222-4222-8222-222222222222",
        "perm": {
            "owner": {"r": True, "w": True, "p": True},
            "group": {"r": True, "w": True, "p": True},
            "others": {"r": True, "w": True, "p": True},
        },
        "depth": 0,
        "ancestors": [],
        "deleted": deleted,
        "cdate": now,
        "mdate": now,
        **fields,
    }
