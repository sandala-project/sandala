from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_query_deep_linkarray_chain_resolves_full_nested_objects():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_stress_dataset(entity_service, node_repo, include_magazine=False)

        rows = node_service.query(
            "library",
            {
                "project": [
                    "name",
                    "slug",
                    "lead_author.*",
                    "lead_author.city.*",
                    "chapters.*",
                    "chapters.reviewer.*",
                    "chapters.reviewer.city.*",
                ],
                "filter": {"entity": "Book", "id": ids["book_alpha"]},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book Alpha"
        assert book["slug"] == "alpha"

        assert book["lead_author"]["id"] == ids["author_anna"]
        assert book["lead_author"]["name"] == "Anna"
        assert book["lead_author"]["level"] == 7
        assert book["lead_author"]["city"]["name"] == "Moscow"
        assert book["lead_author"]["city"]["region_priority"] == 1

        assert len(book["chapters"]) == 2
        by_title = {chapter["title"]: chapter for chapter in book["chapters"]}
        assert sorted(by_title.keys()) == ["Chapter A1", "Chapter A2"]

        chapter_a1 = by_title["Chapter A1"]
        assert chapter_a1["score"] == 9
        assert chapter_a1["reviewer"]["name"] == "Anna"
        assert chapter_a1["reviewer"]["city"]["name"] == "Moscow"
        assert chapter_a1["reviewer"]["city"]["region_priority"] == 1

        chapter_a2 = by_title["Chapter A2"]
        assert chapter_a2["score"] == 8
        assert chapter_a2["reviewer"]["name"] == "Boris"
        assert chapter_a2["reviewer"]["city"]["name"] == "Tula"
        assert chapter_a2["reviewer"]["city"]["region_priority"] == 2


@pytest.mark.integration
def test_query_deep_chain_filter_and_sort_with_tie_breaker():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_stress_dataset(entity_service, node_repo, include_magazine=False)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "lead_author.name", "lead_author.city.name", "chapters.reviewer.city.name"],
                "filter": {
                    "entity": "Book",
                    "chapters.reviewer.city.name": {"in": ["Moscow", "Tula"]},
                    "not": [{"name": {"regex": "Delta$"}}],
                },
                "sort": {"lead_author.city.region_priority": "asc", "slug": "asc", "id": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["alpha", "epsilon", "beta", "zeta"]

        alpha = rows[0]
        assert alpha["name"] == "Book Alpha"
        assert alpha["lead_author"] == {"name": "Anna", "city": {"name": "Moscow"}}
        assert sorted(chapter["reviewer"]["city"]["name"] for chapter in alpha["chapters"]) == ["Moscow", "Tula"]

        epsilon = rows[1]
        assert epsilon["lead_author"]["name"] == "Anna"
        assert epsilon["lead_author"]["city"]["name"] == "Moscow"

        beta = rows[2]
        assert beta["lead_author"]["name"] == "Boris"
        assert beta["lead_author"]["city"]["name"] == "Tula"


@pytest.mark.integration
def test_query_deep_chain_pagination_is_deterministic():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_stress_dataset(entity_service, node_repo, include_magazine=False)

        payload = {
            "project": ["id", "name", "slug", "lead_author.name", "lead_author.city.region_priority"],
            "filter": {"entity": "Book"},
            "sort": {"lead_author.city.region_priority": "asc", "slug": "asc", "id": "asc"},
            "offset": 2,
            "limit": 3,
        }

        first_page = node_service.query("library", payload)
        second_page = node_service.query("library", payload)

        assert first_page == second_page
        assert [row["slug"] for row in first_page] == ["eta", "gamma", "beta"]

        assert first_page[0]["lead_author"] == {"name": "Anna", "city": {"region_priority": 1}}
        assert first_page[1]["lead_author"] == {"name": "Anna", "city": {"region_priority": 1}}
        assert first_page[2]["lead_author"] == {"name": "Boris", "city": {"region_priority": 2}}


@pytest.mark.integration
def test_query_deep_chain_deleted_intermediate_link_becomes_null():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_stress_dataset(entity_service, node_repo, include_magazine=False)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "chapters.*", "chapters.reviewer.*", "chapters.reviewer.city.name"],
                "filter": {"entity": "Book", "id": ids["book_delta"]},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book Delta"
        assert book["slug"] == "delta"
        assert len(book["chapters"]) == 1

        chapter = book["chapters"][0]
        assert chapter["title"] == "Chapter D1"
        assert chapter["score"] == 6
        assert chapter.get("reviewer") is None


@pytest.mark.integration
def test_query_deep_chain_acl_denied_intermediate_link_becomes_null():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_stress_dataset(entity_service, node_repo, include_magazine=False)
        node_repo.collection("library").update_one(
            {"id": ids["author_boris"]},
            {"$set": {"perm.others.r": False}},
        )

        rows = node_service.query(
            "library",
            {
                "project": ["slug", "chapters.title", "chapters.reviewer.name"],
                "filter": {"entity": "Book", "id": ids["book_beta"]},
                "sort": {"slug": "asc"},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["slug"] == "beta"
        by_title = {chapter["title"]: chapter for chapter in book["chapters"]}
        assert by_title["Chapter B1"].get("reviewer") is None
        assert by_title["Chapter C1"]["reviewer"]["name"] == "Clara"


@pytest.mark.integration
def test_query_deep_path_collision_requires_entity_scope():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_stress_dataset(entity_service, node_repo, include_magazine=True)

        with pytest.raises(ValidationError, match="Field collision"):
            node_service.query(
                "library",
                {
                    "project": ["lead_author.city.name"],
                    "sort": {"lead_author.city.name": "asc"},
                },
            )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "lead_author.name", "lead_author.city.name"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
            },
        )

        assert len(rows) == 7
        assert [row["slug"] for row in rows] == ["alpha", "beta", "delta", "epsilon", "eta", "gamma", "zeta"]
        assert rows[0]["lead_author"] == {"name": "Anna", "city": {"name": "Moscow"}}
        assert rows[1]["lead_author"] == {"name": "Boris", "city": {"name": "Tula"}}
        assert rows[2]["lead_author"] == {"name": "Clara", "city": {"name": "Kazan"}}


def _seed_stress_dataset(entity_service, node_repo, *, include_magazine: bool) -> dict[str, str]:
    entity_service.create("library", "City", _city_schema())
    entity_service.create("library", "Author", _author_schema())
    entity_service.create("library", "Chapter", _chapter_schema())
    entity_service.create("library", "Book", _book_schema())
    if include_magazine:
        entity_service.create("library", "Magazine", _magazine_schema())

    now = utc_now_iso()
    ids = {
        "city_moscow": "91000000-0000-4910-8910-000000000001",
        "city_tula": "91000000-0000-4910-8910-000000000002",
        "city_kazan": "91000000-0000-4910-8910-000000000003",
        "author_anna": "91000000-0000-4910-8910-000000000101",
        "author_boris": "91000000-0000-4910-8910-000000000102",
        "author_clara": "91000000-0000-4910-8910-000000000103",
        "author_deleted": "91000000-0000-4910-8910-000000000104",
        "chapter_a1": "91000000-0000-4910-8910-000000000201",
        "chapter_a2": "91000000-0000-4910-8910-000000000202",
        "chapter_b1": "91000000-0000-4910-8910-000000000203",
        "chapter_c1": "91000000-0000-4910-8910-000000000204",
        "chapter_d1": "91000000-0000-4910-8910-000000000205",
        "book_alpha": "91000000-0000-4910-8910-000000001001",
        "book_beta": "91000000-0000-4910-8910-000000001002",
        "book_gamma": "91000000-0000-4910-8910-000000001003",
        "book_delta": "91000000-0000-4910-8910-000000001004",
        "book_epsilon": "91000000-0000-4910-8910-000000001005",
        "book_zeta": "91000000-0000-4910-8910-000000001006",
        "book_eta": "91000000-0000-4910-8910-000000001007",
        "magazine_1": "91000000-0000-4910-8910-000000002001",
    }

    docs = [
        _node(ids["city_moscow"], "City", now, name="Moscow", region_priority=1),
        _node(ids["city_tula"], "City", now, name="Tula", region_priority=2),
        _node(ids["city_kazan"], "City", now, name="Kazan", region_priority=3),
        _node(ids["author_anna"], "Author", now, name="Anna", level=7, city=ids["city_moscow"]),
        _node(ids["author_boris"], "Author", now, name="Boris", level=5, city=ids["city_tula"]),
        _node(ids["author_clara"], "Author", now, name="Clara", level=6, city=ids["city_kazan"]),
        _node(
            ids["author_deleted"],
            "Author",
            now,
            deleted=True,
            name="Ghost Reviewer",
            level=0,
            city=ids["city_moscow"],
        ),
        _node(ids["chapter_a1"], "Chapter", now, title="Chapter A1", score=9, reviewer=ids["author_anna"]),
        _node(ids["chapter_a2"], "Chapter", now, title="Chapter A2", score=8, reviewer=ids["author_boris"]),
        _node(ids["chapter_b1"], "Chapter", now, title="Chapter B1", score=7, reviewer=ids["author_boris"]),
        _node(ids["chapter_c1"], "Chapter", now, title="Chapter C1", score=10, reviewer=ids["author_clara"]),
        _node(ids["chapter_d1"], "Chapter", now, title="Chapter D1", score=6, reviewer=ids["author_deleted"]),
        _node(
            ids["book_alpha"],
            "Book",
            now,
            name="Book Alpha",
            slug="alpha",
            lead_author=ids["author_anna"],
            chapters=[ids["chapter_a1"], ids["chapter_a2"]],
        ),
        _node(
            ids["book_beta"],
            "Book",
            now,
            name="Book Beta",
            slug="beta",
            lead_author=ids["author_boris"],
            chapters=[ids["chapter_b1"], ids["chapter_c1"]],
        ),
        _node(
            ids["book_gamma"],
            "Book",
            now,
            name="Book Gamma",
            slug="gamma",
            lead_author=ids["author_anna"],
            chapters=[ids["chapter_c1"]],
        ),
        _node(
            ids["book_delta"],
            "Book",
            now,
            name="Book Delta",
            slug="delta",
            lead_author=ids["author_clara"],
            chapters=[ids["chapter_d1"]],
        ),
        _node(
            ids["book_epsilon"],
            "Book",
            now,
            name="Book Epsilon",
            slug="epsilon",
            lead_author=ids["author_anna"],
            chapters=[ids["chapter_a1"], ids["chapter_c1"]],
        ),
        _node(
            ids["book_zeta"],
            "Book",
            now,
            name="Book Zeta",
            slug="zeta",
            lead_author=ids["author_boris"],
            chapters=[ids["chapter_b1"]],
        ),
        _node(
            ids["book_eta"],
            "Book",
            now,
            name="Book Eta",
            slug="eta",
            lead_author=ids["author_anna"],
            chapters=[],
        ),
    ]
    if include_magazine:
        docs.append(_node(ids["magazine_1"], "Magazine", now, name="Magazine One", lead_author="Editor Team"))

    node_repo.collection("library").insert_many(docs)
    return ids


def _city_schema() -> dict:
    return {
        "title": "City",
        "description": "City",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "region_priority": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "region_priority"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _author_schema() -> dict:
    return {
        "title": "Author",
        "description": "Author",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "level": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
            "city": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["City"]},
                },
            },
        },
        "required": ["name", "level", "city"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _chapter_schema() -> dict:
    return {
        "title": "Chapter",
        "description": "Chapter",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "score": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
            "reviewer": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Author"]},
                },
            },
        },
        "required": ["title", "score", "reviewer"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _book_schema() -> dict:
    return {
        "title": "Book",
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "slug": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "lead_author": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Author"]},
                },
            },
            "chapters": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "x-meta": {
                    "semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Chapter"]},
                },
            },
        },
        "required": ["name", "slug", "lead_author", "chapters"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _magazine_schema() -> dict:
    return {
        "title": "Magazine",
        "description": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "lead_author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name", "lead_author"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _node(node_id: str, entity: str, now: str, deleted: bool = False, **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": "owner-default",
        "group": "group-default",
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
