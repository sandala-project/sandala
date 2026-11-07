from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from sandala.core.query.filter_compiler import FilterCompiler
from sandala.core.query.semantic_registry import default_semantic_registry
from sandala.core.query.system_fields import SystemFieldProvider
from sandala.core.query_builder import QueryBuilder
from sandala.core.services.node_hooks import NodeHookRegistry


class FakeEntityRepo:
    def __init__(self, module_schemas):
        self.module_schemas = module_schemas

    def get_module_schemas(self, module):
        return self.module_schemas.get(module, {})


def test_module_schemas_are_read_once_per_build_and_reloaded_for_the_next_build():
    from collections import Counter
    from copy import deepcopy

    class CountingRepo(FakeEntityRepo):
        def __init__(self, schemas):
            super().__init__(schemas)
            self.calls = Counter()

        def get_module_schemas(self, module):
            self.calls[module] += 1
            return deepcopy(super().get_module_schemas(module))

    repo = CountingRepo({
        "library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()},
        "users": {"user": _user_schema(), "group": _group_schema()},
    })
    hooks = NodeHookRegistry()

    def require_id(context):
        context.add_required_filter({"id": {"exists": True}})

    hooks.register("before_query", require_id)
    qb = QueryBuilder(repo, hook_registry=hooks)
    query = {
        "filter": {"entity": "Book", "name": "Example", "author.city.name": "Moscow"},
        "project": ["author.city.name", "editors.city.name", "owner.*", "group.*"],
        "sort": {"editors.name": "asc"},
    }
    first_pipeline = qb.build("library", query)
    assert repo.calls == {"library": 1, "users": 1}

    repo.module_schemas["users"]["user"]["properties"]["secret"] = {
        "type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "none"},
    }
    second_pipeline = qb.build("library", query)
    assert repo.calls == {"library": 2, "users": 2}
    assert second_pipeline != first_pipeline
    owner_lookup = next(stage["$lookup"] for stage in second_pipeline
                        if stage.get("$lookup", {}).get("localField") == "owner")
    assert owner_lookup["pipeline"][-1] == {"$unset": ["secret"]}


def _assert_lookup_has_entity_acl_match(match_stage: dict, entities: list[str]) -> None:
    assert "$match" in match_stage
    cond = match_stage["$match"]
    assert "$and" in cond
    and_parts = cond["$and"]
    assert any(part == {"entity": {"$in": entities}} for part in and_parts)
    acl_part = next(part for part in and_parts if isinstance(part, dict) and "$and" in part)
    assert acl_part["$and"][0] == {"deleted": {"$eq": False}}


def _book_schema():
    return {
        "title": "Book",
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
            "editors": {
                "type": "array",
                "items": {"type": "string","format": "uuid"},
                "x-meta": {
                    "semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["Author"]},
                },
            },
            "publisher": {
                "type": "object",
                "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                "properties": {
                    "city": {
                        "type": "string",
                        "format": "uuid",
                        "x-meta": {
                            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                            "link": {"module": "library", "entities": ["City"]},
                        },
                    }
                },
            },
        },
        "required": ["name"],
    }


def _book_schema_with_variants():
    schema = _book_schema()
    schema["properties"]["variants"] = {
        "type": "array",
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        "items": {
            "type": "object",
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            "properties": {
                "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
                "inspector": {
                    "type": "string",
                    "format": "uuid",
                    "x-meta": {
                        "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                        "link": {"module": "library", "entities": ["Author"]},
                    },
                },
            },
        },
    }
    return schema


def _author_schema():
    return {
        "title": "Author",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "city": {
                "type": "string",
                "x-meta": {
                    "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
                    "link": {"module": "library", "entities": ["City"]},
                },
            },
        },
        "required": ["name"],
    }


def _city_schema():
    return {
        "title": "City",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "zip": {"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name"],
    }


def _user_schema():
    return {
        "title": "user",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "username": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
        },
        "required": ["username"],
    }


def _group_schema():
    return {
        "title": "group",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groupname": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "admin"},
            },
        },
        "required": ["groupname"],
    }


def _city_schema_hidden_zip():
    schema = _city_schema()
    schema["properties"]["zip"]["x-meta"]["visibility-mode"] = "admin"
    return schema


def _book_schema_with_hidden_code():
    schema = _book_schema()
    schema["properties"]["internal_code"] = {
        "type": "string",
        "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"},
    }
    return schema


def _book_schema_with_none_field():
    schema = _book_schema()
    schema["properties"]["password_hash"] = {
        "type": "string",
        "x-meta": {"semantic-type": "String", "visibility-mode": "none", "write-mode": "none"},
    }
    return schema


def _magazine_schema_without_publisher():
    return {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["name"],
    }


def _book_schema_with_admin_object_and_all_child():
    schema = _book_schema()
    schema["properties"]["vault"] = {
        "type": "object",
        "additionalProperties": False,
        "x-meta": {"semantic-type": "Object", "visibility-mode": "admin", "write-mode": "admin"},
        "properties": {
            "token": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
    }
    return schema


def _book_schema_with_visible_object_hidden_nested():
    schema = _book_schema()
    schema["properties"]["profile"] = {
        "type": "object",
        "additionalProperties": False,
        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
        "properties": {
            "public": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
            "secret": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "admin"}},
        },
    }
    return schema


def _book_schema_with_structured_media(cover_visibility: str = "all"):
    schema = _book_schema()
    schema["properties"]["cover"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "size": {"type": "integer"},
        },
        "required": ["url"],
        "x-meta": {"semantic-type": "File", "visibility-mode": cover_visibility, "write-mode": cover_visibility},
    }
    schema["properties"]["preview"] = {
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
    }
    schema["properties"]["trailer"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "size": {"type": "integer"},
        },
        "required": ["url", "mime-type", "size"],
        "x-meta": {"semantic-type": "Video", "visibility-mode": "all", "write-mode": "all"},
    }
    return schema


@pytest.mark.parametrize("nullable", [False, True])
@pytest.mark.parametrize("field_schema,eligible", [
    (_book_schema()["properties"]["name"], True),
    ({"type": "array", "items": {"type": "string"}}, True),
    ({"type": "array", "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}, True),
    (_book_schema()["properties"]["publisher"], False),
    (_book_schema_with_variants()["properties"]["variants"], False),
    ({"type": "array", "items": {"anyOf": [
        _book_schema()["properties"]["publisher"], {"type": "null"},
    ]}}, False),
    (_book_schema()["properties"]["author"], False),
    (_book_schema()["properties"]["editors"], False),
    (_book_schema_with_structured_media()["properties"]["cover"], False),
    (_book_schema_with_structured_media()["properties"]["preview"], False),
    (_book_schema_with_structured_media()["properties"]["trailer"], False),
], ids=["scalar", "scalar-array", "nullable-items", "object", "object-array",
        "nullable-object-items", "link", "link-array", "file", "image", "video"])
def test_initial_match_only_pushes_scalars_and_scalar_arrays_in_all_schemas(field_schema, eligible, nullable):
    if nullable:
        field_schema = {"anyOf": [field_schema, {"type": "null"}]}
    compiler = FilterCompiler(FakeEntityRepo({"library": {
        "Candidate": {"properties": {"value": field_schema}},
        "Scalar": {"properties": {"value": {"type": "string"}}},
        "Missing": {"properties": {}},
    }}).get_module_schemas, default_semantic_registry(), SystemFieldProvider())
    system_filter = {"deleted": {"$eq": False}}
    condition = {"value": {"in": [{"nested": "value"}]}}
    compiled_condition = compiler.compile_filter(condition)

    for filter_dsl in (condition, {"and": [condition]}):
        initial_match = compiler.build_initial_match(
            "library", filter_dsl, {"Candidate", "Scalar", "Missing"}, system_filter=system_filter,
        )
        assert initial_match == (
            {"$and": [system_filter, compiled_condition]} if eligible else system_filter
        )

    # Schemas outside the query's entity scope do not disable safe narrowing.
    assert compiler.build_initial_match(
        "library", condition, {"Scalar", "Missing"}, system_filter=system_filter,
    ) == {"$and": [system_filter, compiled_condition]}


def test_initial_match_keeps_container_conditions_only_in_the_final_filter():
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema_with_variants(), "Author": _author_schema(), "City": _city_schema(),
    }}))
    query_filter = {
        "entity": "Book", "name": "Example",
        "publisher": {"eq": {"city": {"name": "Moscow"}}},
        "and": [{"variants": {"in": [{"inspector": {"name": "Anna"}}]}}],
    }
    pipeline = qb.build("library", {
        "filter": query_filter, "project": ["publisher.city.name", "variants.inspector.name"],
    })
    initial_match = pipeline[0]["$match"]
    assert initial_match["$and"][1:] == [
        {"entity": {"$eq": "Book"}}, {"name": {"$eq": "Example"}},
    ]
    compiler = FilterCompiler(FakeEntityRepo({}).get_module_schemas, default_semantic_registry(), SystemFieldProvider())
    final_match = [stage["$match"] for stage in pipeline if "$match" in stage][-1]
    assert compiler.compile_filter(query_filter) in final_match["$and"]


def test_build_default_query_pipeline():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    pipeline = qb.build("library", {})

    assert "$match" in pipeline[0]
    assert pipeline[0]["$match"]["$and"][0] == {"deleted": {"$eq": False}}
    assert pipeline[-2] == {"$sort": {"_id": 1}}
    assert pipeline[-1] == {"$project": {"_id": 0}}


def test_sort_appends_id_tie_breaker_unless_it_is_explicitly_provided():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))

    pipeline = qb.build("library", {"project": ["name"], "sort": {"name": "desc"}})
    assert pipeline[-2] == {"$sort": {"name": -1, "_id": 1}}

    pipeline = qb.build(
        "library",
        {"project": ["name"], "sort": {"name": "desc", "_id": "desc"}},
    )
    assert pipeline[-2] == {"$sort": {"name": -1, "_id": -1}}


def test_no_lookup_builds_single_match_stage_using_final_filter():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    pipeline = qb.build("library", {"project": ["name"], "filter": {"name": "Book A"}})

    matches = [stage for stage in pipeline if "$match" in stage]
    assert len(matches) == 1
    compiled = matches[0]["$match"]
    assert "$and" in compiled
    assert {"name": {"$eq": "Book A"}} in compiled["$and"]


def test_build_adds_lookup_when_project_enters_link():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["*", "author.name"]})
    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    assert root_lookup["$lookup"]["from"] == "library"
    assert root_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "name": 1}}


def test_filter_and_sort_paths_trigger_lookup_but_not_projection_leak():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build(
        "library",
        {
            "project": ["name"],
            "filter": {"author.name": "Tolstoy"},
            "sort": {"author.name": "asc"},
        },
    )

    lookup_stages = [stage for stage in pipeline if "$lookup" in stage]
    assert len(lookup_stages) == 1
    assert pipeline[-1] == {"$project": {"_id": 0, "name": 1}}


def test_entity_filter_narrows_collision_scope():
    mixed_author_schema = {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["author"],
    }
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": mixed_author_schema,
                    "Author": _author_schema(),
                }
            }
        )
    )

    with pytest.raises(ValidationError, match="Field collision"):
        qb.build("library", {"project": ["author.name"]})

    pipeline = qb.build(
        "library",
        {"project": ["author.name"], "filter": {"entity": "Book"}},
    )
    assert any("$lookup" in stage for stage in pipeline)


def test_root_entity_constraint_inside_user_filter_keeps_scope_and_initial_match():
    mixed_author_schema = {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["author"],
    }
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": mixed_author_schema,
                    "Author": _author_schema(),
                }
            }
        )
    )

    pipeline = qb.build(
        "library",
        {
            "project": ["author.name"],
            "filter": {
                "entity": "Book",
                "and": [{"or": [{"entity": "Magazine"}, {"name": "A"}]}],
            },
        },
    )

    assert any("$lookup" in stage for stage in pipeline)
    initial_match = pipeline[0]["$match"]
    assert {"entity": {"$eq": "Book"}} in initial_match["$and"]


@pytest.mark.parametrize("operation", ["project", "filter", "sort"])
@pytest.mark.parametrize("path", ["author", "editors", "publisher.city"])
def test_terminal_references_ignore_target_modules_but_still_check_visibility(path, operation):
    class CountingRepo(FakeEntityRepo):
        def __init__(self, schemas):
            super().__init__(schemas)
            self.reads = []

        def get_module_schemas(self, module):
            self.reads.append(module)
            return super().get_module_schemas(module)

    books = {"A": _book_schema(), "B": _book_schema()}
    for entity, schema in books.items():
        field = schema["properties"]["publisher"]["properties"]["city"] if path == "publisher.city" else schema["properties"][path]
        field["x-meta"]["link"]["module"] = f"targets_{entity}"
    repo = CountingRepo({"library": books})
    qb = QueryBuilder(repo)
    query = {"project": ["name"]}
    query[operation] = [path] if operation == "project" else {path: "target-id" if operation == "filter" else "asc"}

    pipeline = qb.build("library", query)
    assert not any("$lookup" in stage for stage in pipeline)
    assert repo.reads == ["library"]

    for suffix in ("name", "*"):
        with pytest.raises(ValidationError, match="Link module collision"):
            qb.build("library", {"project": [f"{path}.{suffix}"]})

    field["x-meta"]["visibility-mode"] = "none"
    with pytest.raises(ValidationError, match="not visible"):
        qb.build("library", query, actor={"role": "superuser"})


def test_mixed_link_and_scalar_without_descent_does_not_raise_collision():
    mixed_author_schema = {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["author"],
    }
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": mixed_author_schema,
                    "Author": _author_schema(),
                }
            }
        )
    )

    pipeline = qb.build("library", {"project": ["author"]})
    assert pipeline[-1] == {"$project": {"_id": 0, "author": 1}}
    assert not any("$lookup" in stage for stage in pipeline)


def test_mixed_link_and_scalar_terminal_filter_does_not_raise_collision():
    mixed_author_schema = {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["author"],
    }
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": mixed_author_schema,
                    "Author": _author_schema(),
                }
            }
        )
    )

    pipeline = qb.build("library", {"project": ["name"], "filter": {"author": "a1"}})
    assert not any("$lookup" in stage for stage in pipeline)
    assert pipeline[-1] == {"$project": {"_id": 0, "name": 1}}


def test_terminal_link_filter_is_rejected_when_the_same_link_is_resolved():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))

    with pytest.raises(ValidationError, match="Filter path 'author'.*Use 'author.id' instead"):
        qb.build(
            "library",
            {
                "project": ["name", "author.name"],
                "filter": {"author": "a1"},
            },
        )

    pipeline = qb.build(
        "library",
        {
            "project": ["name", "author.name"],
            "filter": {"author.id": "a1"},
        },
    )
    assert any("$lookup" in stage for stage in pipeline)


@pytest.mark.parametrize(
    "payload",
    [
        {"project": ["name"], "filter": {"author": "a1", "author.name": "Leo"}},
        {"project": ["name"], "filter": {"author": "a1"}, "sort": {"author.name": "asc"}},
    ],
)
def test_terminal_link_filter_is_rejected_when_filter_or_sort_resolves_the_link(payload):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))

    with pytest.raises(ValidationError, match="Filter path 'author'.*Use 'author.id' instead"):
        qb.build("library", payload)


def test_terminal_link_array_filter_is_rejected_when_the_same_link_is_resolved():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))

    with pytest.raises(ValidationError, match="Filter path 'editors'.*Use 'editors.id' instead"):
        qb.build(
            "library",
            {
                "project": ["name", "editors.name"],
                "filter": {"editors": "a1"},
            },
        )


def test_terminal_link_array_size_filter_is_rejected_when_the_same_link_is_resolved():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))

    with pytest.raises(ValidationError, match="Filter path 'editors' uses size"):
        qb.build(
            "library",
            {
                "project": ["name", "editors.name"],
                "filter": {"editors": {"size": 2}},
            },
        )

    with pytest.raises(ValidationError, match="Filter path 'editors'.*Use 'editors.id' instead"):
        qb.build(
            "library",
            {
                "project": ["name", "editors.name"],
                "filter": {"editors": {"exists": True}},
            },
        )

    pipeline = qb.build(
        "library",
        {
            "project": ["name", "editors"],
            "filter": {"editors": {"size": 2}},
        },
    )
    assert not any("$lookup" in stage for stage in pipeline)


def test_terminal_nested_link_filter_is_rejected_only_when_that_link_is_resolved():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}})
    )

    pipeline = qb.build(
        "library",
        {
            "project": ["name", "author.name"],
            "filter": {"author.city": "c1"},
        },
    )
    assert any("$lookup" in stage for stage in pipeline)

    with pytest.raises(ValidationError, match="Filter path 'author.city'.*Use 'author.city.id' instead"):
        qb.build(
            "library",
            {
                "project": ["name", "author.city.name"],
                "filter": {"author.city": "c1"},
            },
        )


def test_mixed_link_and_scalar_terminal_sort_does_not_raise_collision():
    mixed_author_schema = {
        "title": "Magazine",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "author": {"type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"}},
        },
        "required": ["author"],
    }
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": mixed_author_schema,
                    "Author": _author_schema(),
                }
            }
        )
    )

    pipeline = qb.build("library", {"project": ["name"], "sort": {"author": "asc"}})
    assert not any("$lookup" in stage for stage in pipeline)
    assert pipeline[-2] == {"$sort": {"author": 1, "_id": 1}}
    assert pipeline[-1] == {"$project": {"_id": 0, "name": 1}}


def test_terminal_link_sort_is_rejected_when_the_same_link_is_resolved():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))

    with pytest.raises(ValidationError, match="Sort path 'author'.*Use 'author.id' instead"):
        qb.build(
            "library",
            {
                "project": ["name", "author.name"],
                "sort": {"author": "asc"},
            },
        )


def test_nested_lookup_under_object_path_supported():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "City": _city_schema()}}))
    pipeline = qb.build("library", {"project": ["publisher.city.name"]})
    assert any("$lookup" in stage for stage in pipeline)


def test_nested_traversal_under_linkarray_supported_with_nested_lookup_pipeline():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["editors.city.name"]})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "editors")
    nested_lookup_stages = [s for s in root_lookup["$lookup"]["pipeline"] if "$lookup" in s]
    assert len(nested_lookup_stages) == 1
    assert nested_lookup_stages[0]["$lookup"]["localField"] == "city"


def test_lookup_projection_preserves_explicit_descendants_under_wildcard_parent():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}}))
    pipeline = qb.build("library", {"project": ["editors.*", "editors.city.name"]})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "editors")
    nested_city_lookup = next(
        s for s in root_lookup["$lookup"]["pipeline"] if "$lookup" in s and s["$lookup"]["localField"] == "city"
    )
    assert nested_city_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "name": 1}}


@pytest.mark.parametrize("field", ["author", "editors"])
def test_lookup_normalizes_reference_and_removes_temporary_result_in_one_stage(field):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": [f"{field}.name"]})

    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    temp = lookup["as"]
    assert temp.startswith("__sandala_lookup_")
    assert lookup["localField"] == field
    updates = [stage["$set"] for stage in pipeline if "$set" in stage]
    resolved = f"${temp}" if field == "editors" else {"$ifNull": [{"$first": f"${temp}"}, None]}
    assert updates == [{field: {"$cond": [
        {"$in": [{"$type": f"${field}"}, ["missing", "null"]]}, f"${field}", resolved,
    ]}, temp: "$$REMOVE"}]
    assert all("$unwind" not in stage for stage in pipeline)
    assert all("$unset" not in stage for stage in pipeline)


def test_root_star_with_link_subfield_limits_lookup_projection():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["*", "author.name"]})
    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    assert root_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "name": 1}}


def test_lookup_projection_keeps_aux_fields_from_filter_and_sort():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}})
    )
    pipeline = qb.build(
        "library",
        {
            "project": ["name", "author.name"],
            "filter": {"author.city.name": "Moscow"},
            "sort": {"author.city.zip": "asc"},
        },
    )
    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    assert root_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "city": 1, "name": 1}}

    nested_city_lookup = next(
        s for s in root_lookup["$lookup"]["pipeline"] if "$lookup" in s and s["$lookup"]["localField"] == "city"
    )
    assert nested_city_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "name": 1, "zip": 1}}


def test_projection_paths_are_normalized_to_prefer_more_specific_paths():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["author", "author.name", "name"]})
    assert pipeline[-1] == {"$project": {"_id": 0, "author.name": 1, "name": 1}}


def test_projection_normalization_handles_deep_paths():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["author", "author.city", "author.city.name"]})
    assert pipeline[-1] == {"$project": {"_id": 0, "author.city.name": 1}}


def test_projection_normalization_resolves_wildcard_parent_collision():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["editors.*", "editors.city.name"]})
    assert pipeline[-1] == {"$project": {"_id": 0, "editors": 1}}


def test_projection_normalization_resolves_plain_parent_collision():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["editors", "editors.city.name"]})
    assert pipeline[-1] == {"$project": {"_id": 0, "editors.city.name": 1}}


def test_lookup_match_is_scoped_by_allowed_link_entities():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["editors.city.name"], "filter": {"entity": "Book"}})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "editors")
    first_match = root_lookup["$lookup"]["pipeline"][0]
    _assert_lookup_has_entity_acl_match(first_match, ["Author"])
    assert root_lookup["$lookup"]["localField"] == "editors"
    assert root_lookup["$lookup"]["foreignField"] == "id"


def test_lookup_match_for_link_is_scoped_by_allowed_entities():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["author.name"], "filter": {"entity": "Book"}})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    first_match = root_lookup["$lookup"]["pipeline"][0]
    _assert_lookup_has_entity_acl_match(first_match, ["Author"])
    assert root_lookup["$lookup"]["localField"] == "author"
    assert root_lookup["$lookup"]["foreignField"] == "id"


def test_parent_lookup_is_scoped_to_all_module_entities():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}})
    )
    pipeline = qb.build("library", {"project": ["parent.name"]})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "parent")
    first_match = root_lookup["$lookup"]["pipeline"][0]
    _assert_lookup_has_entity_acl_match(first_match, ["Author", "Book", "City"])


def test_owner_and_group_system_fields_build_lookup_to_users_module():
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {"Book": _book_schema()},
                "users": {"user": _user_schema(), "group": _group_schema()},
            }
        )
    )
    pipeline = qb.build("library", {"project": ["owner.username", "group.groupname"]})

    owner_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "owner")
    group_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "group")

    assert owner_lookup["$lookup"]["from"] == "users"
    assert group_lookup["$lookup"]["from"] == "users"
    _assert_lookup_has_entity_acl_match(owner_lookup["$lookup"]["pipeline"][0], ["user"])
    _assert_lookup_has_entity_acl_match(group_lookup["$lookup"]["pipeline"][0], ["group"])


def test_ancestors_lookup_is_scoped_to_all_module_entities_without_unwind():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}})
    )
    pipeline = qb.build("library", {"project": ["ancestors.name"]})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "ancestors")
    first_match = root_lookup["$lookup"]["pipeline"][0]
    _assert_lookup_has_entity_acl_match(first_match, ["Author", "Book", "City"])
    assert not any(stage.get("$unwind", {}).get("path") == "$ancestors" for stage in pipeline)


def test_parent_filter_and_sort_trigger_lookup_without_projection_leak():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}})
    )
    pipeline = qb.build(
        "library",
        {
            "project": ["name"],
            "filter": {"parent.name": "Lev"},
            "sort": {"parent.name": "asc"},
        },
    )

    lookup_stages = [stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "parent"]
    assert len(lookup_stages) == 1
    assert pipeline[-2] == {"$sort": {"parent.name": 1, "_id": 1}}
    assert pipeline[-1] == {"$project": {"_id": 0, "name": 1}}


def test_array_object_link_uses_unwind_lookup_and_reassemble():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_variants(), "Author": _author_schema()}}))
    pipeline = qb.build("library", {"project": ["variants.inspector.name"]})

    unwind_stage = next(stage for stage in pipeline if stage.get("$unwind", {}).get("path") == "$variants")
    assert unwind_stage["$unwind"]["includeArrayIndex"].startswith("__sandala_idx_")

    grouped = next(stage for stage in pipeline if "$group" in stage)
    assert grouped["$group"]["_id"] == "$_id"

    assert any("$replaceRoot" in stage for stage in pipeline)
    assert any("$unset" in stage and stage["$unset"] for stage in pipeline)


def test_array_object_link_nested_path_keeps_nested_lookup_pipeline():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema_with_variants(), "Author": _author_schema(), "City": _city_schema()}})
    )
    pipeline = qb.build("library", {"project": ["variants.inspector.city.name"]})

    temp_lookup = next(
        stage
        for stage in pipeline
        if "$lookup" in stage and stage["$lookup"]["as"].startswith("__sandala_lookup_variants__inspector")
    )
    nested_lookup = next(s for s in temp_lookup["$lookup"]["pipeline"] if "$lookup" in s and s["$lookup"]["localField"] == "city")
    assert nested_lookup["$lookup"]["localField"] == "city"
    assert nested_lookup["$lookup"]["foreignField"] == "id"


def test_limit_must_be_positive_integer():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))

    with pytest.raises(ValidationError, match="limit must be positive integer"):
        qb.build("library", {"project": ["name"], "limit": 0})


def test_root_star_excludes_invisible_fields_for_default_all_role():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_hidden_code()}}))

    pipeline = qb.build("library", {"project": "*"})

    assert pipeline[-2] == {"$project": {"_id": 0}}
    assert pipeline[-1] == {"$unset": ["internal_code"]}


def test_lookup_star_excludes_invisible_fields_for_default_all_role():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    pipeline = qb.build("library", {"project": ["publisher.city.*"]})

    publisher_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "publisher.city")
    assert publisher_lookup["$lookup"]["pipeline"][-2] == {"$project": {"_id": 0}}
    assert publisher_lookup["$lookup"]["pipeline"][-1] == {"$unset": ["zip"]}


def test_invisible_fields_raise_on_project_filter_and_sort_for_default_all_role():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["publisher.city.zip"]})

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["name"], "filter": {"publisher.city.zip": {"eq": 123}}})

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["name"], "sort": {"publisher.city.zip": "asc"}})


def test_admin_role_can_access_admin_only_fields():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    pipeline = qb.build("library", {"project": ["publisher.city.zip"]}, actor={"role": "admin"})

    publisher_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "publisher.city")
    assert publisher_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "zip": 1}}


def test_unknown_actor_role_falls_back_to_all_visibility():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["publisher.city.zip"]}, actor={"role": "manager"})


def test_none_actor_role_falls_back_to_all_visibility_and_acl():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["publisher.city.zip"]}, actor={"role": "none"})

    pipeline = qb.build("library", {"project": ["name"]}, actor={"role": "none"})
    first_match = next(stage["$match"] for stage in pipeline if "$match" in stage)
    assert "$and" in first_match
    assert {"deleted": {"$eq": False}} in first_match["$and"]


def test_superuser_cannot_access_none_visibility_field():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_none_field()}}))

    with pytest.raises(ValidationError, match="password_hash"):
        qb.build("library", {"project": ["password_hash"]}, actor={"role": "superuser"})

    with pytest.raises(ValidationError, match="password_hash"):
        qb.build("library", {"project": ["name"], "filter": {"password_hash": {"eq": "hash"}}}, actor={"role": "superuser"})

    with pytest.raises(ValidationError, match="password_hash"):
        qb.build("library", {"project": ["name"], "sort": {"password_hash": "asc"}}, actor={"role": "superuser"})


def test_superuser_star_excludes_none_visibility_field():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_none_field()}}))

    pipeline = qb.build("library", {"project": "*"}, actor={"role": "superuser"})

    assert pipeline[-2] == {"$project": {"_id": 0}}
    assert pipeline[-1] == {"$unset": ["password_hash"]}


def test_system_fields_are_allowed_in_project_filter_and_sort():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_hidden_code()}}))

    pipeline = qb.build("library", {"project": ["id", "entity", "deleted"], "sort": {"id": "asc"}}, actor={"role": "superuser"})

    assert pipeline[-1] == {"$project": {"_id": 0, "deleted": 1, "entity": 1, "id": 1}}


def test_filter_on_deleted_is_rejected_for_all_roles_and_perm_for_non_superuser():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    with pytest.raises(ValidationError, match="deleted field"):
        qb.build("library", {"filter": {"deleted": False}})
    with pytest.raises(ValidationError, match="ACL fields"):
        qb.build("library", {"filter": {"or": [{"name": "A"}, {"perm.owner.r": True}]}})
    with pytest.raises(ValidationError, match="deleted field"):
        qb.build("library", {"filter": {"deleted": False}}, actor={"role": "superuser"})


def test_permission_paths_are_sortable_and_superuser_filterable():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))

    sorted_pipeline = qb.build("library", {"project": ["name"], "sort": {"perm.owner.r": "asc"}})
    filtered_pipeline = qb.build(
        "library",
        {"project": ["name"], "filter": {"perm.group.w": True}},
        actor={"role": "superuser"},
    )

    assert sorted_pipeline[-2] == {"$sort": {"perm.owner.r": 1, "_id": 1}}
    assert filtered_pipeline[0] == {
        "$match": {
            "$and": [
                {"deleted": {"$eq": False}},
                {"perm.group.w": {"$eq": True}},
            ]
        }
    }


def test_superuser_bypasses_permission_acl_but_not_deleted_filter_in_final_and_lookup_match():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    pipeline = qb.build(
        "library",
        {"project": ["author.name"], "filter": {"entity": "Book"}},
        actor={"role": "superuser"},
    )

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    assert root_lookup["$lookup"]["pipeline"][0] == {
        "$match": {"$and": [{"deleted": {"$eq": False}}, {"entity": {"$in": ["Author"]}}]}
    }
    final_match = [stage for stage in pipeline if "$match" in stage][-1]["$match"]
    assert final_match == {"$and": [{"deleted": {"$eq": False}}, {"entity": {"$eq": "Book"}}]}


def test_lookup_path_allowed_when_field_missing_in_some_entities():
    qb = QueryBuilder(
        FakeEntityRepo(
            {
                "library": {
                    "Book": _book_schema(),
                    "Magazine": _magazine_schema_without_publisher(),
                    "City": _city_schema(),
                }
            }
        )
    )

    pipeline = qb.build("library", {"project": ["publisher.city.name"]})

    assert any("$lookup" in stage for stage in pipeline)


def test_invisible_parent_path_segment_is_rejected_even_if_child_marked_all():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_admin_object_and_all_child()}}))

    with pytest.raises(ValidationError, match="vault"):
        qb.build("library", {"project": ["vault.token"]})


def test_explicit_invisible_descendant_fails_even_with_star_on_same_node():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    with pytest.raises(ValidationError, match="publisher.city.zip"):
        qb.build("library", {"project": ["publisher.city.*", "publisher.city.zip"]})


def test_admin_star_lookup_projection_keeps_all_fields_without_explicit_exclusion():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    pipeline = qb.build("library", {"project": ["publisher.city.*"]}, actor={"role": "admin"})

    publisher_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "publisher.city")
    assert publisher_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0}}


def test_recursive_wildcard_excludes_hidden_nested_fields_inside_visible_object():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_visible_object_hidden_nested()}}))

    root_star = qb.build("library", {"project": "*"})
    assert root_star[-2] == {"$project": {"_id": 0}}
    assert root_star[-1] == {"$unset": ["profile.secret"]}

    scoped_star = qb.build("library", {"project": ["profile.*"]})
    assert scoped_star[-2] == {"$project": {"_id": 0, "profile": 1}}
    assert scoped_star[-1] == {"$unset": ["profile.secret"]}


def test_structured_file_image_video_allow_nested_project_filter_sort_paths():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_structured_media()}}))

    pipeline = qb.build(
        "library",
        {
            "project": ["name", "cover.url", "preview.width", "trailer.size"],
            "filter": {"cover.url": "https://cdn/a.pdf", "preview.width": {"gt": 100}},
            "sort": {"trailer.size": "desc"},
        },
    )

    assert not any("$lookup" in stage for stage in pipeline)
    assert pipeline[-2] == {"$sort": {"trailer.size": -1, "_id": 1}}
    assert pipeline[-1] == {"$project": {"_id": 0, "cover.url": 1, "name": 1, "preview.width": 1, "trailer.size": 1}}


def test_structured_types_support_wildcard_projection():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_structured_media()}}))

    pipeline = qb.build("library", {"project": ["cover.*", "preview.*", "trailer.*"]})

    assert pipeline[-1] == {"$project": {"_id": 0, "cover": 1, "preview": 1, "trailer": 1}}


def test_structured_field_visibility_is_controlled_by_parent_field_mode():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_structured_media(cover_visibility="admin")}}))

    with pytest.raises(ValidationError, match="cover"):
        qb.build("library", {"project": ["cover.url"]})

    pipeline = qb.build("library", {"project": ["cover.url"]}, actor={"role": "admin"})
    assert pipeline[-1] == {"$project": {"_id": 0, "cover.url": 1}}


def test_structured_fields_work_in_mixed_projection_filter_sort_with_links():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema_with_structured_media(), "Author": _author_schema(), "City": _city_schema()}})
    )

    pipeline = qb.build(
        "library",
        {
            "project": ["name", "cover.url", "preview.width", "author.name"],
            "filter": {"cover.size": {"gt": 1024}, "author.city.name": "Moscow"},
            "sort": {"preview.width": "desc", "author.name": "asc"},
        },
    )

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    assert root_lookup["$lookup"]["pipeline"][-1] == {"$project": {"_id": 0, "city": 1, "name": 1}}
    assert pipeline[-2] == {"$sort": {"preview.width": -1, "author.name": 1, "_id": 1}}
    assert pipeline[-1] == {"$project": {"_id": 0, "author.name": 1, "cover.url": 1, "name": 1, "preview.width": 1}}


def test_structured_wildcards_mix_with_link_wildcards_and_visibility_unset():
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema_with_structured_media(), "Author": _author_schema(), "City": _city_schema_hidden_zip()}})
    )

    pipeline = qb.build("library", {"project": ["cover.*", "preview.*", "author.city.*"]})

    root_lookup = next(stage for stage in pipeline if "$lookup" in stage and stage["$lookup"]["localField"] == "author")
    nested_city_lookup = next(
        s for s in root_lookup["$lookup"]["pipeline"] if "$lookup" in s and s["$lookup"]["localField"] == "city"
    )
    assert nested_city_lookup["$lookup"]["pipeline"][-2] == {"$project": {"_id": 0}}
    assert nested_city_lookup["$lookup"]["pipeline"][-1] == {"$unset": ["zip"]}

    # The linked City is already sanitized in its own lookup pipeline.
    assert pipeline[-1] == {"$project": {"_id": 0, "author.city": 1, "cover": 1, "preview": 1}}
    assert not any("$unset" in stage for stage in pipeline)


def test_before_query_mutation_is_validated_and_replans_scope_without_changing_input():
    hooks = NodeHookRegistry()
    payload = {"project": ["name"]}
    seen_queries = []
    author_schema = _author_schema()
    # A stale module-wide scope would collide with Book.author during planning.
    author_schema["properties"]["author"] = {
        "type": "string", "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
    }

    def before_query(context):
        if context.is_lookup:
            return
        seen_queries.append(dict(context.query))
        context.query.update({
            "filter": {"entity": "Book"},
            "project": ["author.name"],
            "sort": {"author.name": "desc"},
            "offset": 2,
            "limit": 3,
        })

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": author_schema}}),
        hook_registry=hooks,
    )

    built = qb.build_query("library", payload)

    assert payload == {"project": ["name"]}
    assert seen_queries == [payload]
    assert built.query == {
        "filter": {"entity": "Book"}, "project": ["author.name"],
        "sort": {"author.name": "desc"}, "offset": 2, "limit": 3,
    }
    assert any(stage.get("$lookup", {}).get("localField") == "author" for stage in built.pipeline)
    assert built.pipeline[-4:] == [
        {"$sort": {"author.name": -1, "_id": 1}},
        {"$project": {"_id": 0, "author.name": 1}},
        {"$skip": 2},
        {"$limit": 3},
    ]


def test_before_query_cannot_skip_normal_query_validation():
    hooks = NodeHookRegistry()

    def before_query(context):
        context.query["sort"] = {"name": "sideways"}

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}), hook_registry=hooks)

    with pytest.raises(ValidationError, match="Sort direction"):
        qb.build("library", {"project": ["name"]})


@pytest.mark.parametrize("path", ["author.name", "editors.name", "variants.inspector.name"])
def test_required_filters_reject_reference_descent_including_links_under_arrays(path):
    hooks = NodeHookRegistry()
    hooks.register("before_query", lambda context: context.add_required_filter({path: "Anna"}), module="library")
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema_with_variants(), "Author": _author_schema()}}),
        hook_registry=hooks,
    )

    with pytest.raises(ValidationError, match="cannot traverse link"):
        qb.build("library", {"filter": {"entity": "Book"}, "project": ["name"]})


def test_required_filters_can_use_hidden_stored_fields_and_terminal_references_without_lookups():
    schema = _book_schema_with_variants()
    schema["properties"]["variants"]["items"]["properties"]["name"]["x-meta"]["visibility-mode"] = "none"
    hooks = NodeHookRegistry()

    def before_query(context):
        context.add_required_filter({"variants.name": "private"})
        context.add_required_filter({"variants.inspector": "author-1"})

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema}}), hook_registry=hooks)

    pipeline = qb.build("library", {"project": ["name"]})

    assert not any("$lookup" in stage for stage in pipeline)
    assert pipeline[0]["$match"]["$and"][-1] == {
        "$and": [{"variants.name": {"$eq": "private"}}, {"variants.inspector": {"$eq": "author-1"}}]
    }
    assert pipeline[-1] == {"$project": {"_id": 0, "name": 1}}


def test_required_terminal_link_filter_runs_before_resolution_and_is_not_reapplied_to_object():
    hooks = NodeHookRegistry()

    def before_query(context):
        if not context.is_lookup:
            context.add_required_filter({"author": "author-1"})

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}),
        hook_registry=hooks,
    )

    pipeline = qb.build("library", {"filter": {"entity": "Book"}, "project": ["author.name"]})

    assert pipeline[0]["$match"]["$and"][-1] == {"author": {"$eq": "author-1"}}
    final_match = [stage["$match"] for stage in pipeline if "$match" in stage][-1]
    assert {"author": {"$eq": "author-1"}} not in final_match["$and"]


def test_before_query_runs_for_each_lookup_context_and_collects_local_exclusions():
    hooks = NodeHookRegistry()
    calls = []

    def before_query(context):
        calls.append((context.module, context.path, context.query is None))
        context.exclude_fields("secret")

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(
        FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema(), "City": _city_schema()}}),
        hook_registry=hooks,
    )

    pipeline = qb.build(
        "library", {"filter": {"entity": "Book"}, "project": ["author.city.name", "editors.city.name"]}
    )

    assert calls == [
        ("library", "", False),
        ("library", "author", True),
        ("library", "author.city", True),
        ("library", "editors", True),
        ("library", "editors.city", True),
    ]
    assert set(pipeline[-1]["$unset"]) == {
        "secret", "author.secret", "author.city.secret", "editors.secret", "editors.city.secret",
    }


def test_exclusions_do_not_plan_lookups_and_collapse_parent_child_paths():
    hooks = NodeHookRegistry()

    def before_query(context):
        context.exclude_fields("author", "author.name", "profile.secret", "profile.secret.child")

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}), hook_registry=hooks)

    pipeline = qb.build("library", {"project": "*", "sort": {"name": "asc"}, "offset": 1, "limit": 2})

    assert not any("$lookup" in stage for stage in pipeline)
    assert pipeline[-5:] == [
        {"$sort": {"name": 1, "_id": 1}},
        {"$project": {"_id": 0}},
        {"$unset": ["author", "profile.secret"]},
        {"$skip": 1},
        {"$limit": 2},
    ]


def _book_schema_with_named_array_levels(depth):
    schema = _book_schema()
    modes = {"visibility-mode": "all", "write-mode": "all"}
    item = {"type": "object", "additionalProperties": False,
            "x-meta": {"semantic-type": "Object", **modes},
            "properties": {"editor": schema["properties"]["author"]}}
    field = {"type": "array", "items": item, "x-meta": {"semantic-type": "Array", **modes}}
    for _ in range(depth - 1):
        field = {"type": "array", "x-meta": {"semantic-type": "Array", **modes}, "items": {
            "type": "object", "additionalProperties": False, "properties": {"groups": field},
            "x-meta": {"semantic-type": "Object", **modes},
        }}
    schema["properties"]["matrix"] = field
    return schema


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_named_array_plan_tracks_each_array_path_and_outer_group_indices(depth):
    schema = _book_schema_with_named_array_levels(depth)
    array_paths = ["matrix" + ".groups" * i for i in range(depth)]
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": _author_schema()}}))
    pipeline = qb.build("library", {"filter": {"entity": "Book"}, "project": [f"{array_paths[-1]}.editor.name"]})

    unwinds = [stage["$unwind"] for stage in pipeline if "$unwind" in stage]
    assert [stage["path"] for stage in unwinds] == [f"${path}" for path in array_paths]
    indices = [stage["includeArrayIndex"] for stage in unwinds]
    assert len(set(indices)) == depth
    groups = [stage["$group"]["_id"] for stage in pipeline if "$group" in stage]
    assert len(groups) == depth
    for i, key in zip(reversed(range(depth)), groups):
        assert key == ({"node": "$_id", **{f"i{j}": f"${indices[j]}" for j in range(i)}} if i else "$_id")
    assert sum("$lookup" in stage for stage in pipeline) == 1


@pytest.mark.parametrize("other_kind", ["Object", "ArrayScalar"])
def test_array_container_collisions_require_entity_scope_only_for_descent(other_kind):
    first = _book_schema_with_named_array_levels(1)
    second = _book_schema_with_named_array_levels(1)
    if other_kind == "Object":
        second["properties"]["matrix"] = second["properties"]["matrix"]["items"]
    else:
        second["properties"]["matrix"]["items"] = second["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {"One": first, "Two": second, "Author": _author_schema()}}))
    with pytest.raises(ValidationError, match="Field collision"):
        qb.build("library", {"project": ["matrix.editor.name"]})
    pipeline = qb.build("library", {"project": ["matrix"]})
    assert not any("$lookup" in stage for stage in pipeline)
    scoped = qb.build("library", {"filter": {"entity": "One"}, "project": ["matrix.editor.name"]})
    assert sum("$lookup" in stage for stage in scoped) == 1


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_required_filter_cannot_traverse_reference_below_named_array_levels(depth):
    hooks = NodeHookRegistry()
    path = "matrix" + ".groups" * (depth - 1) + ".editor"

    def policy(context):
        context.add_required_filter({f"{path}.name": "Anna"})

    hooks.register("before_query", policy, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema_with_named_array_levels(depth), "Author": _author_schema(),
    }}), hook_registry=hooks)
    with pytest.raises(ValidationError, match=f"Required filter cannot traverse link '{path}'"):
        qb.build("library", {"filter": {"entity": "Book"}, "project": ["*"]})


def test_nullable_array_object_items_support_link_descent_and_visibility():
    schema = _book_schema_with_named_array_levels(1)
    item = schema["properties"]["matrix"]["items"]
    item["properties"]["secret"] = {"type": "string", "x-meta": {
        "semantic-type": "String", "visibility-mode": "none", "write-mode": "none",
    }}
    schema["properties"]["matrix"]["items"] = {"anyOf": [{"type": "null"}, item]}
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": _author_schema()}}))
    pipeline = qb.build("library", {"filter": {"entity": "Book"}, "project": ["matrix.*", "matrix.editor.name"]})
    assert sum("$lookup" in stage for stage in pipeline) == 1
    assert pipeline[-1] == {"$unset": ["matrix.secret"]}


def _schema_with_hidden_container_fields(container_type, nullable):
    schema = _book_schema_with_visible_object_hidden_nested()
    field = schema["properties"]["profile"]
    for name in ("id", "entity", "parent", "ancestors", "depth", "deleted", "cdate", "mdate"):
        field["properties"][name] = {
            "type": "string", "x-meta": {
                "semantic-type": "String", "visibility-mode": "none", "write-mode": "none",
            },
        }
    if nullable:
        field = {"anyOf": [{"type": "null"}, field]}
    if container_type == "Array":
        field = {"type": "array", "items": field, "x-meta": {
            "semantic-type": "Array", "visibility-mode": "all", "write-mode": "all",
        }}
    schema["properties"]["profile"] = field
    return schema


@pytest.mark.parametrize("container_type", ["Object", "Array"])
@pytest.mark.parametrize("nullable", [False, True])
@pytest.mark.parametrize("project", [["profile"], ["profile.*"], ["*"]])
def test_container_projection_excludes_hidden_children_including_system_field_names(container_type, nullable, project):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _schema_with_hidden_container_fields(container_type, nullable)}}))

    pipeline = qb.build("library", {"project": project})

    assert pipeline[-1] == {"$unset": sorted(f"profile.{name}" for name in (
        "secret", "id", "entity", "parent", "ancestors", "depth", "deleted", "cdate", "mdate",
    ))}
    assert not any("$lookup" in stage for stage in pipeline)


@pytest.mark.parametrize("project", [["name"], ["profile.public"]])
def test_visibility_exclusions_skip_paths_absent_from_final_projection(project):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _schema_with_hidden_container_fields("Array", True)}}))

    pipeline = qb.build("library", {"project": project})

    assert not any("$unset" in stage for stage in pipeline)


@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("container_type", ["Object", "Array"])
def test_plain_container_projection_inside_nested_lookup_excludes_hidden_children(depth, container_type):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema(), "Author": _author_schema(),
        "City": _schema_with_hidden_container_fields(container_type, True),
    }}))
    path = "publisher.city" if depth == 1 else "author.city"

    pipeline = qb.build("library", {"filter": {"entity": "Book"}, "project": [f"{path}.profile"]})

    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    if depth == 2:
        lookup = next(stage["$lookup"] for stage in lookup["pipeline"] if "$lookup" in stage)
    assert "profile.secret" in lookup["pipeline"][-1]["$unset"]
    assert "profile.id" in lookup["pipeline"][-1]["$unset"]
    assert pipeline[-1] == {"$project": {"_id": 0, f"{path}.profile": 1}}


def test_narrow_lookup_projection_does_not_add_unnecessary_visibility_unset():
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema(), "Author": _schema_with_hidden_container_fields("Array", True),
    }}))

    pipeline = qb.build("library", {"filter": {"entity": "Book"}, "project": ["author.name"]})

    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    assert not any("$unset" in stage for stage in lookup["pipeline"])
    assert not any("$unset" in stage for stage in pipeline)


@pytest.mark.parametrize("project", [["profile"], ["*"]])
def test_mixed_reference_and_object_fields_still_exclude_hidden_object_children(project):
    other = _book_schema()
    other["properties"]["profile"] = other["properties"]["author"]
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "One": _book_schema_with_visible_object_hidden_nested(), "Two": other, "Author": _author_schema(),
    }}))

    pipeline = qb.build("library", {"project": project})

    assert pipeline[-1] == {"$unset": ["profile.secret"]}
    assert not any("$lookup" in stage for stage in pipeline)


@pytest.mark.parametrize("path", ["$expr", "$where", "name.$expr", "profile..secret", "name\x00", "*", "name.*"])
@pytest.mark.parametrize("operation", ["filter", "sort"])
def test_query_rejects_non_dsl_field_paths(path, operation):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema_with_none_field()}}))
    query = {"project": ["name"], operation: {path: {"eq": [{"$substrCP": ["$password_hash", 0, 1]}, "A"]}
                                          if operation == "filter" else "asc"}}
    with pytest.raises(ValidationError, match="Invalid field path"):
        qb.build("library", query)


@pytest.mark.parametrize("scope", ["library", "empty"])
def test_mongo_expression_filter_is_rejected_even_with_empty_entity_scope(scope):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    with pytest.raises(ValidationError, match="Invalid field path"):
        qb.build(scope, {"filter": {"entity": "Missing", "or": [{"$expr": {"eq": [1, 1]}}]}})


@pytest.mark.parametrize("path", ["name.*.child", "author.$expr", "*.name", "author..name"])
def test_projection_rejects_invalid_path_syntax(path):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    with pytest.raises(ValidationError, match="Invalid field path"):
        qb.build("library", {"project": ["*", path]})


@pytest.mark.parametrize("path", ["unknown", "profile.0.secret", "profile.unknown", "profile.public.child",
                                  "profile.owner.username", "author.profile.0.secret"])
@pytest.mark.parametrize("operation", ["project", "filter", "sort"])
def test_query_requires_complete_schema_paths_including_lookup_targets(path, operation):
    schema = _schema_with_hidden_container_fields("Array", True)
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": schema}}))
    query = {"project": ["name"], "filter": {"entity": "Book"}}
    if operation == "project":
        query["project"] = [path]
    else:
        query[operation] = {path: {"eq": "guess"} if operation == "filter" else "asc"}
        query["filter"]["entity"] = "Book"
    with pytest.raises(ValidationError):
        qb.build("library", query)


@pytest.mark.parametrize("container_type", ["Object", "Array"])
@pytest.mark.parametrize("operator", ["eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "regex", "sort"])
def test_container_value_operations_cannot_infer_hidden_descendants(container_type, operator):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _schema_with_hidden_container_fields(container_type, True),
    }}))
    query = {"project": ["id"]}
    if operator == "sort":
        query["sort"] = {"profile": "asc"}
    else:
        query["filter"] = {"not": [{"profile": {operator: {"public": "known", "secret": "guess"}}}]}
    with pytest.raises(ValidationError, match="not visible"):
        qb.build("library", query, actor={"role": "superuser"})


@pytest.mark.parametrize("path", ["publisher.city.profile", "author.city.profile", "editors.city.profile"])
@pytest.mark.parametrize("operation", ["filter", "sort"])
def test_container_visibility_checks_apply_inside_lookup_scopes(path, operation):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema(), "Author": _author_schema(), "City": _book_schema_with_visible_object_hidden_nested(),
    }}))
    query = {"project": ["name"], "filter": {"entity": "Book"}}
    if operation == "filter":
        query["filter"][path] = {"eq": {"public": "known", "secret": "guess"}}
    else:
        query["sort"] = {path: "asc"}
    with pytest.raises(ValidationError, match=path) as error:
        qb.build("library", query)
    assert "secret" not in str(error.value)


def test_container_visibility_checks_every_schema_even_when_first_field_is_scalar():
    scalar = _book_schema()
    scalar["properties"]["profile"] = scalar["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "A": scalar, "B": _book_schema_with_visible_object_hidden_nested(),
    }}))
    with pytest.raises(ValidationError, match="profile.*not visible"):
        qb.build("library", {"project": ["name"], "sort": {"profile": "asc"}})


def test_container_presence_and_size_do_not_require_visibility_of_contents():
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _schema_with_hidden_container_fields("Array", True)}}))
    pipeline = qb.build("library", {
        "project": ["profile.public"], "filter": {"profile": {"exists": True, "size": 2}},
    })
    assert not any("$lookup" in stage for stage in pipeline)
    assert {"$and": [{"profile": {"$exists": True}}, {"profile": {"$size": 2}}]} in pipeline[0]["$match"]["$and"]
    with pytest.raises(ValidationError, match="not visible"):
        qb.build("library", {"filter": {"profile": {"exists": True, "eq": []}}})


def test_container_value_operations_use_actor_visibility_not_output_exclusions():
    schema = _book_schema_with_visible_object_hidden_nested()
    hooks = NodeHookRegistry()
    hooks.register("before_query", lambda context: context.exclude_fields("profile"), module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema}}), hook_registry=hooks)
    pipeline = qb.build("library", {
        "project": ["name"], "filter": {"profile": {"eq": {"public": "p", "secret": "s"}}},
        "sort": {"profile": "asc"},
    }, actor={"role": "admin"})
    assert pipeline[-1] == {"$unset": ["profile"]}
    assert not any("$lookup" in stage for stage in pipeline)


def test_required_filters_can_compare_containers_with_hidden_contents():
    hooks = NodeHookRegistry()
    hooks.register("before_query", lambda context: context.add_required_filter({
        "profile": {"eq": {"public": "p", "secret": "s"}},
    }), module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema_with_visible_object_hidden_nested(),
    }}), hook_registry=hooks)
    pipeline = qb.build("library", {"project": ["name"]})
    assert {"profile": {"$eq": {"public": "p", "secret": "s"}}} in pipeline[0]["$match"]["$and"]


def test_scalar_arrays_numeric_object_properties_and_literal_values_remain_queryable():
    schema = _book_schema()
    schema["properties"]["tags"] = {"type": "array", "items": schema["properties"]["name"], "x-meta": {
        "semantic-type": "Array", "visibility-mode": "all",
    }}
    schema["properties"]["publisher"]["properties"]["0"] = schema["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": _book_schema_with_none_field()}}))
    pipeline = qb.build("library", {
        "project": ["name", "publisher.0"], "filter": {
            "entity": "Book", "tags": {"eq": ["one", "$expr"]}, "author": "author-id", "publisher.0": "literal",
        }, "sort": {"tags": "asc"},
    })
    assert not any("$lookup" in stage for stage in pipeline)


@pytest.mark.parametrize("array_path", ["profile", "editors"])
def test_numeric_object_properties_cannot_be_misinterpreted_as_array_indices(array_path):
    schema = _schema_with_hidden_container_fields("Array", False)
    numeric_object = _book_schema_with_visible_object_hidden_nested()["properties"]["profile"]
    # Even a declared numeric property does not permit Mongo's array indexing:
    # profile.0.secret addresses the first item's secret, not its '0' object.
    schema["properties"]["profile"]["items"]["properties"]["0"] = numeric_object
    author = _author_schema()
    author["properties"]["0"] = numeric_object
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": author}}))
    with pytest.raises(ValidationError, match="Array indices"):
        qb.build("library", {"filter": {"entity": "Book", f"{array_path}.0.public": "guess"}})


def test_numeric_object_properties_remain_queryable_through_single_links():
    author = _author_schema()
    author["properties"]["0"] = author["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": author}}))
    pipeline = qb.build("library", {
        "project": ["author.0"], "filter": {"entity": "Book", "author.0": "literal"},
    })
    assert any(stage.get("$lookup", {}).get("localField") == "author" for stage in pipeline)


@pytest.mark.parametrize("operation", ["project", "filter", "sort"])
def test_complete_paths_can_be_missing_from_some_entity_schemas(operation):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "Book": _book_schema_with_variants(), "Magazine": _magazine_schema_without_publisher(),
    }}))
    query = {"project": ["name"], operation: ["variants.name"] if operation == "project" else {
        "variants.name": "A" if operation == "filter" else "asc",
    }}
    pipeline = qb.build("library", query)
    assert not any("$lookup" in stage for stage in pipeline)


def test_filter_compiler_itself_rejects_mongo_expression_field_names():
    compiler = FilterCompiler(FakeEntityRepo({}).get_module_schemas, default_semantic_registry(), SystemFieldProvider())
    with pytest.raises(ValidationError, match="Invalid field path"):
        compiler.compile_filter({"or": [{"$expr": {"eq": ["$password_hash", "guess"]}}]})


def test_container_content_checks_do_not_load_link_target_schemas():
    class CountingRepo(FakeEntityRepo):
        def __init__(self, schemas):
            super().__init__(schemas)
            self.modules = []

        def get_module_schemas(self, module):
            self.modules.append(module)
            return super().get_module_schemas(module)

    schema = _book_schema()
    schema["properties"]["publisher"]["properties"]["city"]["x-meta"]["link"]["module"] = "locations"
    repo = CountingRepo({"library": {"Book": schema}})
    qb = QueryBuilder(repo)
    query = {"project": ["name"], "filter": {"publisher": {"eq": {"city": "city-id"}}}, "sort": {"publisher": "asc"}}
    pipeline = qb.build("library", query)
    assert set(repo.modules) == {"library"}
    assert not any("$lookup" in stage for stage in pipeline)


def _schema_with_target_scope(entities):
    schema = _book_schema_with_variants()
    for field in (schema["properties"]["author"], schema["properties"]["editors"],
                  schema["properties"]["publisher"]["properties"]["city"],
                  schema["properties"]["variants"]["items"]["properties"]["inspector"]):
        field["x-meta"]["link"]["entities"] = entities
    return schema


@pytest.mark.parametrize("path", ["author", "editors", "publisher.city", "variants.inspector"])
def test_lookup_preserves_and_groups_target_scopes_by_source_entity(path):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "A": _schema_with_target_scope([]), "B": _schema_with_target_scope(["Author"]),
        "C": _schema_with_target_scope(["Author"]), "D": _schema_with_target_scope(["City"]),
        "Author": _author_schema(), "City": _city_schema(),
    }}))
    pipeline = qb.build("library", {"filter": {"entity": {"in": ["A", "B", "C", "D"]}}, "project": [f"{path}.name"]})
    lookups = [stage["$lookup"] for stage in pipeline if "$lookup" in stage]
    assert len(lookups) == 1
    lookup = lookups[0]
    assert lookup["let"] == {"source_entity": "$entity"}
    assert lookup["pipeline"][0]["$match"]["$and"][1] == {"entity": {"$in": ["Author", "City"]}}
    assert lookup["pipeline"][0]["$match"]["$and"][-1] == {"$expr": {"$or": [
        {"$and": [{"$in": ["$$source_entity", {"$literal": ["B", "C"]}]},
                  {"$in": ["$entity", {"$literal": ["Author"]}]}]},
        {"$and": [{"$in": ["$$source_entity", {"$literal": ["D"]}]},
                  {"$in": ["$entity", {"$literal": ["City"]}]}]},
    ]}}


@pytest.mark.parametrize("entities", [[], ["Author"]])
def test_identical_target_scopes_do_not_add_lookup_variables_or_expressions(entities):
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "A": _schema_with_target_scope(entities), "B": _schema_with_target_scope(entities), "Author": _author_schema(),
    }}))
    pipeline = qb.build("library", {"project": ["author.name"]})
    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    assert "let" not in lookup
    assert len(lookup["pipeline"][0]["$match"]["$and"]) == 2
    assert lookup["pipeline"][0]["$match"]["$and"][1] == {"entity": {"$in": entities}}


@pytest.mark.parametrize("operation", ["project", "filter", "sort"])
def test_empty_explicit_scope_does_not_traverse_unrelated_colliding_schemas(operation):
    book = _schema_with_target_scope([])
    book["properties"]["city"] = book["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {"A": book, "Author": _author_schema(), "City": _city_schema()}}))
    query = {"filter": {"entity": "A"}, "project": ["name"]}
    if operation == "project":
        query["project"] = ["author.city.name"]
    elif operation == "filter":
        query["filter"]["author.city.name"] = "Moscow"
    else:
        query["sort"] = {"author.city.name": "asc"}
    pipeline = qb.build("library", query)
    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    assert lookup["pipeline"][0]["$match"]["$and"][1] == {"entity": {"$in": []}}
    assert not any("$lookup" in stage for stage in lookup["pipeline"])


def test_source_and_target_entity_names_in_lookup_expressions_are_literals():
    qb = QueryBuilder(FakeEntityRepo({"library": {
        "$A": _schema_with_target_scope([]), "$B": _schema_with_target_scope(["$Author"]), "$Author": _author_schema(),
    }}))
    pipeline = qb.build("library", {"project": ["author.name"]})
    lookup = next(stage["$lookup"] for stage in pipeline if "$lookup" in stage)
    assert lookup["pipeline"][0]["$match"]["$and"][-1] == {"$expr": {"$and": [
        {"$in": ["$$source_entity", {"$literal": ["$B"]}]},
        {"$in": ["$entity", {"$literal": ["$Author"]}]},
    ]}}


@pytest.mark.parametrize("project", [["_id"], ["*", "_id"], ["_id.*"], ["name", "_id.child"]])
@pytest.mark.parametrize("empty_scope", [False, True])
def test_mongo_id_cannot_be_explicitly_projected_even_in_empty_scopes(project, empty_scope):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    query = {"project": project}
    if empty_scope:
        query["filter"] = {"entity": "Missing"}
    with pytest.raises(ValidationError, match="MongoDB '_id'"):
        qb.build("library", query)


@pytest.mark.parametrize("path", ["author._id", "editors._id", "author.city._id", "publisher.city._id",
                                  "variants.inspector._id", "parent._id", "ancestors._id", "owner._id", "group._id"])
@pytest.mark.parametrize("operation", ["project", "filter", "sort"])
def test_queries_cannot_access_mongo_ids_through_references(path, operation):
    qb = QueryBuilder(FakeEntityRepo({
        "library": {"Book": _book_schema_with_variants(), "Author": _author_schema(), "City": _city_schema()},
        "users": {"user": _user_schema(), "group": _group_schema()},
    }))
    query = {"project": ["*"], "filter": {"entity": "Book"}}
    if operation == "project":
        query["project"] = ["*", path]
    elif operation == "filter":
        query["filter"][path] = "mongo-id"
    else:
        query["sort"] = {path: "asc"}
    with pytest.raises(ValidationError, match="MongoDB '_id'"):
        qb.build("library", query)


@pytest.mark.parametrize("path", ["author._id", "editors._id.*"])
def test_empty_reference_scopes_do_not_allow_mongo_id_projection(path):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _schema_with_target_scope([])}}))
    with pytest.raises(ValidationError, match="MongoDB '_id'"):
        qb.build("library", {"project": [path]})


def test_user_object_id_fields_remain_queryable_at_root_inside_arrays_and_through_links():
    schema = _book_schema_with_variants()
    for properties in (schema["properties"]["publisher"]["properties"], schema["properties"]["variants"]["items"]["properties"]):
        properties["_id"] = schema["properties"]["name"]
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": schema, "Author": schema}}))
    paths = ["publisher._id", "variants._id", "author.publisher._id", "editors.variants._id"]
    pipeline = qb.build("library", {
        "filter": {"entity": "Book", **{path: "user-id" for path in paths}},
        "project": paths, "sort": {**{path: "asc" for path in paths}, "_id": "desc"},
    })
    assert pipeline[-2]["$sort"]["_id"] == -1
    assert pipeline[-1] == {"$project": {"_id": 0, **{path: 1 for path in sorted(paths)}}}


@pytest.mark.parametrize("op,operand", [
    *[(op, value) for op in ("in", "nin") for value in (None, True, 1, 1.5, "A", {}, ("A",))],
    *[("exists", value) for value in (None, 0, 1, "true", [], {})],
    *[("size", value) for value in (None, True, False, -1, 1.5, "0", [], {})],
    *[("regex", value) for value in (None, True, 1, [], {})],
])
@pytest.mark.parametrize("field", ["name", "author.name"])
def test_filter_operand_types_are_checked_inside_nested_logical_groups(op, operand, field):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}))
    with pytest.raises(ValidationError, match=f"Operator '{op}'"):
        qb.build("library", {
            "project": ["name"], "filter": {"entity": "Book", "and": [{"or": [{field: {op: operand}}]}]},
        })


@pytest.mark.parametrize("op,operand,mongo_op", [
    ("in", [], "$in"), ("in", ["A", None], "$in"), ("nin", [], "$nin"),
    ("exists", True, "$exists"), ("exists", False, "$exists"),
    ("size", 0, "$size"), ("size", 2, "$size"), ("regex", "", "$regex"), ("regex", "^A", "$regex"),
])
def test_filter_operand_type_checks_preserve_valid_boundary_values(op, operand, mongo_op):
    compiler = FilterCompiler(FakeEntityRepo({}).get_module_schemas, default_semantic_registry(), SystemFieldProvider())
    assert compiler.compile_filter({"field": {op: operand}}) == {"field": {mongo_op: operand}}


@pytest.mark.parametrize("op", ["eq", "neq", "gt", "gte", "lt", "lte"])
@pytest.mark.parametrize("operand", [None, True, 0, 1.5, "A", [], {"caption": "A"}])
def test_comparison_operators_do_not_impose_new_operand_type_restrictions(op, operand):
    compiler = FilterCompiler(FakeEntityRepo({}).get_module_schemas, default_semantic_registry(), SystemFieldProvider())
    mongo_op = "$ne" if op == "neq" else f"${op}"
    assert compiler.compile_filter({"field": {op: operand}}) == {"field": {mongo_op: operand}}


@pytest.mark.parametrize("parameter", ["limit", "offset"])
@pytest.mark.parametrize("value", [True, False, "1", 1.5, -1, [], {}])
def test_pagination_requires_integers_and_does_not_accept_booleans(parameter, value):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    with pytest.raises(ValidationError, match=parameter):
        qb.build("library", {parameter: value})


@pytest.mark.parametrize("parameter,stage", [("limit", "$limit"), ("offset", "$skip")])
def test_pagination_accepts_the_maximum_signed_int64_value(parameter, stage):
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}))
    pipeline = qb.build("library", {parameter: 2**63 - 1})
    assert {stage: 2**63 - 1} in pipeline


@pytest.mark.parametrize("parameter", ["limit", "offset"])
@pytest.mark.parametrize("value", [2**63, 2**80])
@pytest.mark.parametrize("from_hook", [False, True])
def test_pagination_rejects_int64_overflow_in_requests_and_hooks(parameter, value, from_hook):
    hooks = NodeHookRegistry()

    def before_query(context):
        context.query[parameter] = value

    if from_hook:
        hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}), hook_registry=hooks)
    with pytest.raises(ValidationError, match=f"{parameter} must not exceed"):
        qb.build("library", {} if from_hook else {parameter: value})


@pytest.mark.parametrize("lookup", [False, True])
def test_required_filters_also_validate_operand_types_in_root_and_lookup_hooks(lookup):
    hooks = NodeHookRegistry()

    def before_query(context):
        if context.is_lookup == lookup:
            context.add_required_filter({"name": {"regex": None}})

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema(), "Author": _author_schema()}}), hook_registry=hooks)
    with pytest.raises(ValidationError, match="Operator 'regex'"):
        qb.build("library", {"project": ["author.name"], "filter": {"entity": "Book"}})


@pytest.mark.parametrize("parameter", ["limit", "offset"])
def test_boolean_pagination_injected_by_before_query_is_rejected(parameter):
    hooks = NodeHookRegistry()

    def before_query(context):
        context.query[parameter] = True

    hooks.register("before_query", before_query, module="library")
    qb = QueryBuilder(FakeEntityRepo({"library": {"Book": _book_schema()}}), hook_registry=hooks)
    with pytest.raises(ValidationError, match=parameter):
        qb.build("library", {})
