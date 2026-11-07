from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_query_star_excludes_invisible_fields_for_all_role():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["*", "author.name", "author.city.*", "owner.username", "group.groupname"],
                "filter": {"entity": "Book", "id": ids["book"]},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Visible Book"
        assert "internal_code" not in row

        assert row["author"]["name"] == "Anna"
        assert row["author"]["city"]["name"] == "Moscow"
        assert "zip" not in row["author"]["city"]
        assert row["owner"]["username"] == "admin"
        assert row["group"]["groupname"] == "default"
        assert "email" not in row["owner"]


@pytest.mark.integration
def test_query_invisible_fields_raise_on_project_filter_sort_for_all_role():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)

        with pytest.raises(ValidationError, match="author.city.zip"):
            node_service.query(
                "library",
                {
                    "project": ["author.city.zip"],
                    "filter": {"entity": "Book", "id": ids["book"]},
                },
            )

        with pytest.raises(ValidationError, match="author.city.zip"):
            node_service.query(
                "library",
                {
                    "project": ["name"],
                    "filter": {"entity": "Book", "author.city.zip": {"eq": 101000}},
                },
            )

        with pytest.raises(ValidationError, match="author.city.zip"):
            node_service.query(
                "library",
                {
                    "project": ["name"],
                    "filter": {"entity": "Book"},
                    "sort": {"author.city.zip": "asc"},
                },
            )
        with pytest.raises(ValidationError, match="owner.email"):
            node_service.query(
                "library",
                {
                    "project": ["name", "owner.email"],
                    "filter": {"entity": "Book", "id": ids["book"]},
                },
            )
        with pytest.raises(ValidationError, match="group.is_default"):
            node_service.query(
                "library",
                {
                    "project": ["name", "group.is_default"],
                    "filter": {"entity": "Book", "id": ids["book"]},
                },
            )


@pytest.mark.integration
def test_query_admin_role_can_access_admin_only_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "internal_code", "author.city.zip", "owner.email", "group.is_default"],
                "filter": {"entity": "Book", "id": ids["book"]},
            },
            actor={"role": "admin"},
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Visible Book"
        assert row["internal_code"] == "SECRET-42"
        assert row["author"]["city"]["zip"] == 101000
        assert row["owner"]["email"] is None
        assert row["group"]["is_default"] is True


@pytest.mark.integration
def test_query_structured_fields_work_in_mixed_project_filter_sort():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "cover.url", "preview.width", "trailer.size", "author.name"],
                "filter": {"entity": "Book", "id": ids["book"], "cover.size": {"gte": 5000}},
                "sort": {"preview.width": "desc", "trailer.size": "asc"},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Visible Book"
        assert row["cover"]["url"] == "https://cdn.example/cover.pdf"
        assert row["preview"]["width"] == 640
        assert row["trailer"]["size"] == 120000
        assert row["author"]["name"] == "Anna"


@pytest.mark.integration
def test_query_structured_visibility_is_controlled_by_parent_field():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)

        with pytest.raises(ValidationError, match="secret_file"):
            node_service.query(
                "library",
                {
                    "project": ["secret_file.url"],
                    "filter": {"entity": "Book", "id": ids["book"]},
                },
            )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "secret_file.url", "secret_file.size"],
                "filter": {"entity": "Book", "id": ids["book"], "secret_file.size": {"gte": 100}},
            },
            actor={"role": "admin"},
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Visible Book"
        assert row["secret_file"]["url"] == "https://cdn.example/secret.pdf"
        assert row["secret_file"]["size"] == 777


@pytest.mark.integration
def test_query_admin_visibility_still_respects_acl_and_superuser_bypasses():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_visibility_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["book"]},
            {"$set": {"perm.others.r": False}},
        )

        rows_admin = node_service.query(
            "library",
            {
                "project": ["name", "internal_code"],
                "filter": {"entity": "Book", "id": ids["book"]},
            },
            actor={"role": "admin"},
        )
        assert rows_admin == []

        rows_superuser = node_service.query(
            "library",
            {
                "project": ["name", "internal_code"],
                "filter": {"entity": "Book", "id": ids["book"]},
            },
            actor={"role": "superuser"},
        )
        assert len(rows_superuser) == 1
        assert rows_superuser[0]["internal_code"] == "SECRET-42"


def _visibility_object_schema():
    modes = {"visibility-mode": "all", "write-mode": "all"}
    properties = {
        "public": {"type": "string", "x-meta": {"semantic-type": "String", **modes}},
        "admin_secret": {"type": "string", "x-meta": {
            "semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin",
        }},
    }
    for name in ("id", "entity", "parent", "ancestors", "depth", "deleted", "cdate", "mdate"):
        properties[name] = {"type": "string", "x-meta": {
            "semantic-type": "String", "visibility-mode": "none", "write-mode": "none",
        }}
    return {"anyOf": [{"type": "null"}, {
        "type": "object", "additionalProperties": False, "properties": properties,
        "x-meta": {"semantic-type": "Object", **modes},
    }]}


@pytest.mark.integration
def test_plain_container_projections_hide_descendants_at_root_and_each_lookup_level():
    with mongo_services() as (entity_service, service, repo):
        ids = _seed_visibility_dataset(entity_service, repo)
        modes = {"visibility-mode": "all", "write-mode": "all"}
        raw_profile = {"public": "visible", "admin_secret": "admin-only", **{
            name: "never-visible" for name in ("id", "entity", "parent", "ancestors", "depth", "deleted", "cdate", "mdate")
        }}
        raw_fields = {
            "profile": raw_profile,
            "sections": [None, raw_profile],
            "matrix": [{"children": [None, raw_profile]}, {"children": []}],
        }
        for entity in ("Book", "Author", "City"):
            schema = entity_service.get_schema("library", entity)
            sections = {"type": "array", "items": _visibility_object_schema(), "x-meta": {"semantic-type": "Array", **modes}}
            schema["properties"].update({
                "profile": _visibility_object_schema(), "sections": sections,
                "matrix": {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
                    "type": "object", "additionalProperties": False, "properties": {"children": sections},
                    "x-meta": {"semantic-type": "Object", **modes},
                }},
            })
            entity_service.update("library", entity, schema)
            repo.collection("library").update_one({"id": ids[entity.lower()]}, {"$set": raw_fields})

        for actor in (None, {"role": "admin"}, {"role": "superuser"}):
            expected_profile = {"public": "visible", **({"admin_secret": "admin-only"} if actor else {})}
            expected = {
                "profile": expected_profile,
                "sections": [None, expected_profile],
                "matrix": [{"children": [None, expected_profile]}, {"children": []}],
            }
            for project in (["profile", "sections", "matrix"], ["profile.*", "sections.*", "matrix.*"], ["*"]):
                row = service.query("library", {"filter": {"entity": "Book", "id": ids["book"]}, "project": project}, actor=actor)[0]
                assert {key: row[key] for key in expected} == expected

            row = service.query("library", {
                "filter": {"entity": "Book", "id": ids["book"]},
                "project": ["author.profile", "author.sections", "author.city.profile", "author.city.matrix"],
            }, actor=actor)[0]
            assert row["author"]["profile"] == expected["profile"]
            assert row["author"]["sections"] == expected["sections"]
            assert row["author"]["city"]["profile"] == expected["profile"]
            assert row["author"]["city"]["matrix"] == expected["matrix"]
            node = service.get("library", ids["book"], actor=actor)
            assert {key: node[key] for key in expected} == expected
            listed = service.list_entity("library", "Book", {}, actor=actor)
            assert {key: listed[0][key] for key in expected} == expected

        for path in ("profile.id", "sections.parent", "author.profile.id", "author.city.sections.entity"):
            for options in ({"project": [path]}, {"filter": {"entity": "Book", path: "value"}}, {"sort": {path: "asc"}}):
                with pytest.raises(ValidationError, match="not visible"):
                    service.query("library", {"filter": {"entity": "Book"}, **options})
        assert repo.find_by_id("library", ids["book"])["profile"] == raw_profile


@pytest.mark.integration
def test_mixed_reference_and_container_entities_hide_children_without_changing_raw_links():
    with mongo_services() as (entity_service, service, repo):
        ids = _seed_visibility_dataset(entity_service, repo)
        modes = {"visibility-mode": "all", "write-mode": "all"}
        schema = entity_service.get_schema("library", "Book")
        schema["properties"].update({
            "profile": _visibility_object_schema(),
            "sections": {"type": "array", "items": _visibility_object_schema(), "x-meta": {"semantic-type": "Array", **modes}},
        })
        entity_service.update("library", "Book", schema)
        repo.collection("library").update_one({"id": ids["book"]}, {"$set": {
            "profile": {"public": "visible", "id": "hidden", "admin_secret": "hidden"},
            "sections": [{"public": "visible", "id": "hidden", "admin_secret": "hidden"}],
        }})
        other_schema = _author_schema()
        other_schema["properties"].update({
            "profile": {"type": "string", "format": "uuid", "x-meta": {
                "semantic-type": "Link", **modes, "link": {"module": "library", "entities": ["Author"]},
            }},
            "sections": {"type": "array", "items": {"type": "string", "format": "uuid"}, "x-meta": {
                "semantic-type": "LinkArray", **modes, "link": {"module": "library", "entities": ["Author"]},
            }},
        })
        entity_service.create("library", "Other", other_schema)
        repo.collection("library").insert_one(_node(
            "a1000000-0000-4900-8900-000000002001", "Other", utc_now_iso(),
            name="Other", profile=ids["author"], sections=[ids["author"]],
        ))
        for project in (["profile", "sections"], ["*"]):
            rows = service.query("library", {"filter": {"entity": {"in": ["Book", "Other"]}}, "project": project, "sort": {"name": "asc"}})
            assert rows[0]["profile"] == ids["author"]
            assert rows[0]["sections"] == [ids["author"]]
            assert rows[1]["profile"] == {"public": "visible"}
            assert rows[1]["sections"] == [{"public": "visible"}]


@pytest.mark.integration
def test_query_rejects_visibility_oracles_and_preserves_safe_container_operations():
    with mongo_services() as (entity_service, service, repo):
        ids = _seed_visibility_dataset(entity_service, repo)
        modes = {"visibility-mode": "all", "write-mode": "all"}
        sections = {"type": "array", "items": _visibility_object_schema(), "x-meta": {"semantic-type": "Array", **modes}}
        profile = {"public": "visible", "admin_secret": "admin-only", "id": "never-visible"}
        fields = {"profile": profile, "sections": [None, profile], "matrix": [{"children": [profile]}]}
        for entity in ("Book", "Author", "City"):
            schema = entity_service.get_schema("library", entity)
            schema["properties"].update({
                "profile": _visibility_object_schema(), "sections": sections,
                "matrix": {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
                    "type": "object", "additionalProperties": False, "properties": {"children": sections},
                    "x-meta": {"semantic-type": "Object", **modes},
                }},
            })
            entity_service.update("library", entity, schema)
            repo.collection("library").update_one({"id": ids[entity.lower()]}, {"$set": fields})

        queries = [
            {"filter": {"$expr": {"eq": [{"$substrCP": ["$internal_code", 0, 1]}, "S"]}}},
            {"filter": {"or": [{"$expr": {"eq": ["$profile.id", "never-visible"]}}]}},
        ]
        for path in ("sections.0.id", "matrix.0.children.id", "matrix.children.0.id", "author.sections.0.id",
                     "author.city.matrix.children.0.id", "editors.0.name", "profile.unknown"):
            queries.extend([{"project": [path]}, {"filter": {path: "guess"}}, {"sort": {path: "asc"}}])
        for path in ("profile", "sections", "matrix", "matrix.children", "author.profile", "author.city.sections"):
            queries.extend([{"filter": {path: {"eq": profile}}}, {"sort": {path: "asc"}}])
        for actor in (None, {"role": "superuser"}):
            for options in queries:
                query = {"project": ["id"], **options}
                query["filter"] = {"entity": "Book", **query.get("filter", {})}
                with pytest.raises(ValidationError):
                    service.query("library", query, actor=actor)

        rows = service.query("library", {
            "project": ["id", "profile", "sections"],
            "filter": {"entity": "Book", "profile": {"exists": True}, "sections": {"size": 2}},
        })
        assert rows == [{"id": ids["book"], "profile": {"public": "visible"}, "sections": [None, {"public": "visible"}]}]
        rows = service.query("library", {
            "project": ["id"], "filter": {"entity": "Book", "cover": {"eq": repo.find_by_id("library", ids["book"])["cover"]}},
            "sort": {"cover": "asc"},
        })
        assert rows == [{"id": ids["book"]}]

        def required_filter(context):
            context.add_required_filter({"profile": {"eq": profile}})

        service.hooks.register("before_query", required_filter, module="library")
        rows = service.query("library", {"project": ["id", "author.name"], "filter": {"entity": "Book"}})
        assert rows == [{"id": ids["book"], "author": {"name": "Anna"}}]


def _seed_visibility_dataset(entity_service, node_repo) -> dict[str, str]:
    entity_service.create("library", "City", _city_schema())
    entity_service.create("library", "Author", _author_schema())
    entity_service.create("library", "Book", _book_schema())

    now = utc_now_iso()
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

    ids = {
        "city": "a1000000-0000-4900-8900-000000000001",
        "author": "a1000000-0000-4900-8900-000000000101",
        "book": "a1000000-0000-4900-8900-000000001001",
    }

    node_repo.collection("library").insert_many(
        [
            _node(ids["city"], "City", now, name="Moscow", zip=101000),
            _node(
                ids["author"],
                "Author",
                now,
                owner=root_user["id"],
                group=default_group["id"],
                name="Anna",
                city=ids["city"],
            ),
            _node(
                ids["book"],
                "Book",
                now,
                owner=root_user["id"],
                group=default_group["id"],
                name="Visible Book",
                author=ids["author"],
                internal_code="SECRET-42",
                cover={
                    "url": "https://cdn.example/cover.pdf",
                    "mime-type": "application/pdf",
                    "size": 5555,
                },
                preview={
                    "url": "https://cdn.example/preview.jpg",
                    "mime-type": "image/jpeg",
                    "width": 640,
                    "height": 360,
                    "size": 2048,
                },
                trailer={
                    "url": "https://cdn.example/trailer.mp4",
                    "mime-type": "video/mp4",
                    "size": 120000,
                },
                secret_file={
                    "url": "https://cdn.example/secret.pdf",
                    "mime-type": "application/pdf",
                    "size": 777,
                },
            ),
        ]
    )
    return ids


def _city_schema() -> dict:
    return {
        "title": "City",
        "description": "City",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "zip": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "admin", "write-mode": "admin"}},
        },
        "required": ["name", "zip"],
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
            "city": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["City"]},
                },
            },
        },
        "required": ["name", "city"],
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
            "author": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Author"]},
                },
            },
            "internal_code": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
            },
            "cover": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["url"],
                "x-meta": {"semantic-type": "File", "visibility-mode": "all", "write-mode": "all"},
            },
            "preview": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "size": {"type": "integer"},
                },
                "required": ["url", "mime-type", "width", "height", "size"],
                "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
            },
            "trailer": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["url", "mime-type", "size"],
                "x-meta": {"semantic-type": "Video", "visibility-mode": "all", "write-mode": "all"},
            },
            "secret_file": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string"},
                    "mime-type": {"type": "string"},
                    "size": {"type": "integer"},
                },
                "required": ["url"],
                "x-meta": {"semantic-type": "File", "visibility-mode": "admin", "write-mode": "admin"},
            },
        },
        "required": ["name", "author"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _node(
    node_id: str,
    entity: str,
    now: str,
    deleted: bool = False,
    owner: str = "11111111-1111-4111-8111-111111111111",
    group: str = "22222222-2222-4222-8222-222222222222",
    **fields,
):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": owner,
        "group": group,
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
