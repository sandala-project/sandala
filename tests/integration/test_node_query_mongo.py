from __future__ import annotations

import pytest

from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


CITY_1_ID = "11111111-1111-4111-8111-111111111111"
CITY_2_ID = "22222222-2222-4222-8222-222222222222"
VILLAGE_1_ID = "33333333-3333-4333-8333-333333333333"
AUTHOR_1_ID = "44444444-4444-4444-8444-444444444444"
AUTHOR_2_ID = "55555555-5555-4555-8555-555555555555"
AUTHOR_DELETED_ID = "66666666-6666-4666-8666-666666666666"
BOOK_1_ID = "77777777-7777-4777-8777-777777777777"
OWNER_ID = "88888888-8888-4888-8888-888888888888"
GROUP_ID = "99999999-9999-4999-8999-999999999999"


@pytest.mark.integration
def test_query_resolves_nested_linkarray_paths_with_real_mongo():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_entities(entity_service)
        _seed_nodes(node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "editors.*", "editors.city.name"],
                "filter": {"entity": "Book", "name": "Book A"},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book A"
        assert isinstance(book.get("editors"), list)

        editor_names = sorted(editor["name"] for editor in book["editors"])
        assert editor_names == ["Anna", "Boris"]

        city_names = sorted(editor["city"]["name"] for editor in book["editors"])
        assert city_names == ["Moscow", "Tula"]

        # Deleted linked authors must not be resolved.
        assert len(book["editors"]) == 2


@pytest.mark.integration
def test_query_linkarray_resolve_respects_updated_link_entities():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_entities(entity_service)
        _seed_nodes(node_repo)

        entity_service.update("library", "Book", _book_schema(editor_entities=[]))

        rows = node_service.query(
            "library",
            {
                "project": ["name", "editors.name"],
                "filter": {"entity": "Book", "name": "Book A"},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book A"
        assert book["editors"] == []


@pytest.mark.integration
def test_query_nested_link_resolve_respects_updated_link_entities():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_entities(entity_service)
        _seed_nodes(node_repo)

        entity_service.update("library", "Author", _author_schema(city_entities=[]))

        rows = node_service.query(
            "library",
            {
                "project": ["name", "editors.name", "editors.city.name"],
                "filter": {"entity": "Book", "name": "Book A"},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book A"
        assert sorted(editor["name"] for editor in book["editors"]) == ["Anna", "Boris"]
        assert all(editor.get("city") is None for editor in book["editors"])


@pytest.mark.integration
def test_query_nested_link_resolve_respects_partially_narrowed_link_entities():
    with mongo_services() as (entity_service, node_service, node_repo):
        entity_service.create("library", "City", _city_schema())
        entity_service.create("library", "Village", _village_schema())
        entity_service.create("library", "Author", _author_schema(city_entities=["City", "Village"]))
        entity_service.create("library", "Book", _book_schema())

        now = utc_now_iso()
        node_repo.collection("library").insert_many(
            [
                _node(CITY_1_ID, "City", now, name="Moscow"),
                _node(VILLAGE_1_ID, "Village", now, name="Yasnaya Polyana"),
                _node(AUTHOR_1_ID, "Author", now, name="Anna", city=CITY_1_ID),
                _node(AUTHOR_2_ID, "Author", now, name="Boris", city=VILLAGE_1_ID),
                _node(BOOK_1_ID, "Book", now, name="Book A", editors=[AUTHOR_1_ID, AUTHOR_2_ID]),
            ]
        )

        before = node_service.query(
            "library",
            {
                "project": ["name", "editors.name", "editors.city.name"],
                "filter": {"entity": "Book", "name": "Book A"},
            },
        )
        assert len(before) == 1
        before_book = before[0]
        before_cities = {editor["name"]: editor["city"]["name"] for editor in before_book["editors"]}
        assert before_cities == {"Anna": "Moscow", "Boris": "Yasnaya Polyana"}

        entity_service.update("library", "Author", _author_schema(city_entities=["City"]))

        after = node_service.query(
            "library",
            {
                "project": ["name", "editors.name", "editors.city.name"],
                "filter": {"entity": "Book", "name": "Book A"},
            },
        )
        assert len(after) == 1
        after_book = after[0]
        by_name = {editor["name"]: editor.get("city") for editor in after_book["editors"]}
        assert by_name["Anna"]["name"] == "Moscow"
        assert by_name["Boris"] is None


@pytest.mark.integration
def test_target_scopes_are_bound_to_each_source_entity_at_every_lookup_depth():
    with mongo_services() as (entities, service, repo):
        modes = {"visibility-mode": "all", "write-mode": "all"}

        def reference(kind, allowed):
            field = {"x-meta": {"semantic-type": kind, **modes, "link": {"module": "library", "entities": allowed}}}
            field.update({"type": "string", "format": "uuid"} if kind == "Link" else
                         {"type": "array", "items": {"type": "string", "format": "uuid"}})
            return field

        def object_field(properties):
            return {"type": "object", "additionalProperties": False, "properties": properties,
                    "x-meta": {"semantic-type": "Object", **modes}}

        def array_field(items):
            return {"type": "array", "items": items, "x-meta": {"semantic-type": "Array", **modes}}

        def pair(allowed):
            return {"single": reference("Link", allowed), "multiple": reference("LinkArray", allowed)}

        entities.create("library", "City", _city_schema())
        entities.create("library", "Village", _village_schema())
        for entity, allowed in (("Author", ["City"]), ("Editor", ["Village"])):
            schema = _city_schema()
            schema["properties"].update({"city": reference("Link", allowed), "cities": reference("LinkArray", allowed)})
            entities.create("library", entity, schema)
        scopes = {"A": [], "B": ["Author"], "C": ["Author", "Editor"], "D": ["Editor"], "E": ["Author"]}
        for entity, allowed in scopes.items():
            schema = _city_schema()
            schema["properties"].update(pair(allowed))
            nested = {**pair(allowed), "entity": schema["properties"]["name"]}
            schema["properties"].update({
                "details": object_field(nested),
                "sections": array_field(object_field({"teams": array_field(object_field(nested))})),
            })
            entities.create("library", entity, schema)

        now = utc_now_iso()
        hidden_id = "81000000-0000-4100-8100-000000000100"
        hidden = _node(hidden_id, "Author", now, name="Hidden", city=VILLAGE_1_ID, cities=[CITY_1_ID, VILLAGE_1_ID])
        hidden["perm"]["others"]["r"] = False
        repo.collection("library").insert_many([
            _node(CITY_1_ID, "City", now, name="Moscow"),
            _node(VILLAGE_1_ID, "Village", now, name="Village"),
            _node(AUTHOR_1_ID, "Author", now, name="Anna", city=VILLAGE_1_ID, cities=[CITY_1_ID, VILLAGE_1_ID]),
            _node(AUTHOR_2_ID, "Editor", now, name="Editor", city=CITY_1_ID, cities=[CITY_1_ID, VILLAGE_1_ID]),
            _node(AUTHOR_DELETED_ID, "Author", now, deleted=True, name="Deleted", cities=[]), hidden,
        ])
        ids = {}
        for index, entity in enumerate(scopes, 1):
            ids[entity] = f"81000000-0000-4100-8100-{index:012d}"
            links = {"single": AUTHOR_2_ID if entity in {"B", "D"} else AUTHOR_1_ID,
                     "multiple": [AUTHOR_1_ID, AUTHOR_2_ID, AUTHOR_DELETED_ID, hidden_id]}
            repo.collection("library").insert_one(_node(
                ids[entity], entity, now, name=entity, **links,
                details={**links, "entity": "not-the-source"},
                sections=[{"teams": [{**links, "entity": "not-the-source"}, {**links, "entity": "wrong-again"}]}],
            ))

        paths = ["single", "multiple", "details.single", "details.multiple",
                 "sections.teams.single", "sections.teams.multiple"]
        project = ["id", "entity", *[f"{path}.{field}" for path in paths for field in ("name", "city.name", "cities.name")]]

        def read(predicate, actor):
            rows = service.query("library", {"project": project, "filter": predicate, "sort": {"id": "asc"}}, actor=actor)
            for row in rows:
                for value in (row, row["details"], *row["sections"][0]["teams"]):
                    value["multiple"].sort(key=lambda target: target["name"])
            return rows

        for actor in (None, {"role": "superuser"}):
            baseline = None
            for predicate in ({"entity": {"in": list(scopes)}}, {"and": [{"entity": {"in": list(scopes)}}]},
                              {"id": {"in": list(ids.values())}}):
                rows = read(predicate, actor)
                assert len(rows) == len(scopes)
                if baseline is None:
                    baseline = rows
                assert rows == baseline
            for row in baseline:
                entity = row["entity"]
                expected = set()
                if "Author" in scopes[entity]:
                    expected.add("Anna")
                    if actor:
                        expected.add("Hidden")
                if "Editor" in scopes[entity]:
                    expected.add("Editor")
                for value in (row, row["details"], *row["sections"][0]["teams"]):
                    assert {target["name"] for target in value["multiple"]} == expected
                    assert (value.get("single") or {}).get("name") == {"C": "Anna", "D": "Editor", "E": "Anna"}.get(entity)
                    targets = [*value["multiple"], *([value["single"]] if value.get("single") else [])]
                    for target in targets:
                        assert target.get("city") is None
                        assert target["cities"] == [{"name": "Village" if target["name"] == "Editor" else "Moscow"}]
                for predicate in ({"entity": entity}, {"and": [{"entity": entity}]}):
                    assert read(predicate, actor) == [row]

        # Filters and sorts also resolve links, without requesting them in project.
        for entity in ("A", "B", "C", "D", "E"):
            rows = service.query("library", {
                "project": ["entity"], "filter": {"and": [{"entity": entity}], "multiple.name": "Anna"},
                "sort": {"multiple.name": "asc"},
            })
            assert rows == ([{"entity": entity}] if "Author" in scopes[entity] else [])


@pytest.mark.integration
def test_empty_explicit_scope_never_traverses_unrelated_colliding_schemas():
    with mongo_services() as (entities, service, repo):
        _seed_entities(entities)
        _seed_nodes(repo)
        schema = _book_schema(editor_entities=[])
        schema["properties"]["author"] = {"type": "string", "format": "uuid", "x-meta": {
            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
            "link": {"module": "library", "entities": []},
        }}
        schema["properties"]["city"] = schema["properties"]["name"]
        entities.update("library", "Book", schema)
        repo.collection("library").update_one({"id": BOOK_1_ID}, {"$set": {"author": AUTHOR_1_ID}})
        for reference in ("author", "editors"):
            path = f"{reference}.city.name"
            for options in ({"project": ["name", path]}, {"project": ["name", path], "sort": {path: "asc"}}):
                rows = service.query("library", {"filter": {"entity": "Book"}, **options})
                assert len(rows) == 1
                assert rows[0].get(reference) == ([] if reference == "editors" else None)
            assert service.query("library", {"filter": {"entity": "Book", path: "Moscow"}}) == []


def _city_schema() -> dict:
    return {
        "title": "City",
        "description": "City",
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


def _village_schema() -> dict:
    return {
        "title": "Village",
        "description": "Village",
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


def _author_schema(city_entities: list[str] | None = None) -> dict:
    allowed_city_entities = city_entities if city_entities is not None else ["City"]
    return {
        "title": "Author",
        "description": "Author",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
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
        "required": ["name", "city"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _book_schema(editor_entities: list[str] | None = None) -> dict:
    allowed_editor_entities = editor_entities if editor_entities is not None else ["Author"]
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
            "editors": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "x-meta": {
                    "semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": allowed_editor_entities},
                },
            },
        },
        "required": ["name", "editors"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _seed_entities(entity_service) -> None:
    entity_service.create("library", "City", _city_schema())
    entity_service.create("library", "Author", _author_schema())
    entity_service.create("library", "Book", _book_schema())


def _seed_nodes(node_repo) -> None:
    now = utc_now_iso()
    docs = [
        _node(CITY_1_ID, "City", now, name="Moscow"),
        _node(CITY_2_ID, "City", now, name="Tula"),
        _node(AUTHOR_1_ID, "Author", now, name="Anna", city=CITY_1_ID),
        _node(AUTHOR_2_ID, "Author", now, name="Boris", city=CITY_2_ID),
        _node(AUTHOR_DELETED_ID, "Author", now, deleted=True, name="Ghost", city=CITY_1_ID),
        _node(BOOK_1_ID, "Book", now, name="Book A", editors=[AUTHOR_1_ID, AUTHOR_2_ID, AUTHOR_DELETED_ID]),
    ]
    node_repo.collection("library").insert_many(docs)


def _node(node_id: str, entity: str, now: str, deleted: bool = False, **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": OWNER_ID,
        "group": GROUP_ID,
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
