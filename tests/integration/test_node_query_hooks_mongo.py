from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from sandala.core.errors import NotFoundError, QueryValidationError
from tests.integration.helpers import mongo_services
from tests.integration.query_dataset import author_schema, book_schema, seed_query_dataset


pytestmark = pytest.mark.integration


@pytest.fixture
def query_services():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo, include_magazine=False)
        yield entity_service, node_service, node_repo, ids


@pytest.mark.parametrize("actor", [None, {"role": "superuser"}], ids=["anonymous", "superuser"])
@pytest.mark.parametrize("resolve", [False, True], ids=["raw", "resolved"])
def test_required_filters_intersect_user_filter_and_always_hide_deleted(query_services, actor, resolve):
    _entity_service, service, repo, ids = query_services
    repo.collection("library").update_one({"id": ids["book_deleted"]}, {"$set": {"rating": 5}})

    def before_query(context):
        if not context.is_lookup:
            context.add_required_filter({"pages": {"gte": 150}})
            context.add_required_filter({"rating": {"gte": 4}})

    service.hooks.register("before_query", before_query, module="library")
    project = ["slug", "author.name"] if resolve else ["slug"]
    rows = service.query(
        "library",
        {
            "project": project,
            "filter": {"entity": "Book", "or": [{"slug": {"in": ["beta", "gamma", "deleted"]}}, {"pages": {"lt": 50}}]},
        },
        actor=actor,
    )

    assert [row["slug"] for row in rows] == ["gamma"]
    if resolve:
        assert rows[0]["author"] == {"name": "Clara"}
    assert service.query(
        "library", {"filter": {"entity": "Book", "pages": {"lt": 150}}, "project": project}, actor=actor
    ) == []


def test_required_filters_and_exclusions_survive_later_query_replacement(query_services):
    _entity_service, service, _repo, _ids = query_services

    def restrict(context):
        context.add_required_filter({"pages": {"gte": 150}})
        context.exclude_fields("rating")

    def replace(context):
        context.query = {"filter": {"entity": "Book"}, "project": ["slug", "rating"], "sort": {"slug": "asc"}}

    service.hooks.register("before_query", restrict, module="library", priority=10)
    service.hooks.register("before_query", replace, module="library", priority=20)

    assert service.query("library", {}) == [{"slug": "beta"}, {"slug": "delta"}, {"slug": "gamma"}]


@pytest.mark.parametrize("resolve", [False, True], ids=["raw", "resolved"])
def test_required_filter_on_link_id_uses_stored_value_even_when_link_is_resolved(query_services, resolve):
    _entity_service, service, _repo, ids = query_services

    def before_query(context):
        if not context.is_lookup:
            context.add_required_filter({"author": ids["author_anna"]})

    service.hooks.register("before_query", before_query, module="library")
    rows = service.query(
        "library",
        {"filter": {"entity": "Book"}, "project": ["slug", "author.name" if resolve else "author"], "sort": {"slug": "asc"}},
    )

    assert [row["slug"] for row in rows] == ["alpha", "delta"]
    assert all(row["author"] == ({"name": "Anna"} if resolve else ids["author_anna"]) for row in rows)


def test_module_policy_applies_at_each_nested_lookup_and_when_targets_are_queried_directly(query_services):
    _entity_service, service, _repo, ids = query_services
    before_calls = []
    after_calls = []

    def before_query(context):
        before_calls.append((context.module, context.path, context.query is None))
        context.add_required_filter({"or": [{"entity": {"neq": "Author"}}, {"age": {"gte": 34}}]})
        context.add_required_filter({"or": [{"entity": {"neq": "City"}}, {"zip": 101000}]})
        context.exclude_fields("age", "zip")

    service.hooks.register("before_query", before_query, module="library")
    service.hooks.register("after_query", lambda context: after_calls.append(context.path), module="library")
    rows = service.query(
        "library",
        {"filter": {"entity": "Book", "slug": "alpha"}, "project": ["slug", "author.*", "author.city.*", "editors.*", "editors.city.*"]},
    )

    assert len(rows) == 1
    book = rows[0]
    assert book["author"]["name"] == "Anna"
    assert "age" not in book["author"]
    assert book["author"]["city"]["name"] == "Moscow"
    assert "zip" not in book["author"]["city"]
    editors = {editor["name"]: editor for editor in book["editors"]}
    assert set(editors) == {"Anna", "Boris"}
    assert all("age" not in editor for editor in editors.values())
    assert editors["Anna"]["city"]["name"] == "Moscow"
    assert "zip" not in editors["Anna"]["city"]
    assert editors["Boris"].get("city") is None
    assert before_calls == [
        ("library", "", False),
        ("library", "author", True),
        ("library", "author.city", True),
        ("library", "editors", True),
        ("library", "editors.city", True),
    ]
    assert after_calls == [""]

    authors = service.query("library", {"filter": {"entity": "Author"}, "project": "*", "sort": {"name": "asc"}})
    assert [author["name"] for author in authors] == ["Anna", "Boris"]
    assert all("age" not in author for author in authors)
    assert [author["city"] for author in authors] == [ids["city_moscow"], ids["city_tula"]]


def test_lookup_exclusions_preserve_fields_until_outer_filter_sort_and_pagination(query_services):
    _entity_service, service, _repo, _ids = query_services

    def before_query(context):
        context.exclude_fields("age")

    service.hooks.register("before_query", before_query, module="library")
    rows = service.query(
        "library",
        {
            "filter": {"entity": "Book", "author.age": {"gte": 34}},
            "project": ["slug", "author.name", "author.age"],
            "sort": {"author.age": "desc", "slug": "asc"},
            "offset": 1,
            "limit": 1,
        },
    )

    assert rows == [{"slug": "alpha", "author": {"name": "Anna"}}]


@pytest.mark.parametrize("reference", ["author", "editors"], ids=["link", "linkarray"])
def test_excluded_field_behind_two_links_still_drives_outer_filter_sort_and_page(query_services, reference):
    _entity_service, service, _repo, _ids = query_services
    city_path = f"{reference}.city"

    def before_query(context):
        context.add_required_filter({"or": [{"entity": {"neq": "City"}}, {"zip": {"gte": 101000}}]})
        context.exclude_fields("zip")

    service.hooks.register("before_query", before_query, module="library")
    rows = service.query(
        "library",
        {
            "filter": {"entity": "Book", f"{city_path}.zip": {"gte": 200000}},
            "project": ["slug", f"{reference}.name", f"{city_path}.name", f"{city_path}.zip"],
            "sort": {f"{city_path}.zip": "desc", "slug": "asc"},
            "offset": 1,
            "limit": 1,
        },
    )

    if reference == "author":
        assert rows == [{"slug": "beta", "author": {"name": "Boris", "city": {"name": "Tula"}}}]
    else:
        assert len(rows) == 1
        assert rows[0]["slug"] == "alpha"
        assert len(rows[0]["editors"]) == 2
        assert {editor["name"]: editor for editor in rows[0]["editors"]} == {
            "Anna": {"name": "Anna", "city": {"name": "Moscow"}},
            "Boris": {"name": "Boris", "city": {"name": "Tula"}},
        }


def test_excluding_fields_under_links_does_not_implicitly_resolve_them(query_services):
    _entity_service, service, _repo, ids = query_services
    service.hooks.register("before_query", lambda context: context.exclude_fields("author.age", "editors.age"), module="library")

    rows = service.query("library", {"filter": {"entity": "Book", "slug": "alpha"}, "project": "*"})

    assert len(rows) == 1
    assert rows[0]["author"] == ids["author_anna"]
    assert rows[0]["editors"] == [ids["author_anna"], ids["author_boris"], ids["author_deleted"], ids["author_missing"]]


def test_required_filters_can_read_hidden_fields_without_exposing_or_unlocking_them(query_services):
    entity_service, service, _repo, _ids = query_services
    schema = author_schema()
    schema["properties"]["age"]["x-meta"]["visibility-mode"] = "none"
    entity_service.update("library", "Author", schema)

    def before_query(context):
        context.add_required_filter({"age": {"gte": 34}})
        context.exclude_fields("pen_name")

    service.hooks.register("before_query", before_query, module="library")
    rows = service.query("library", {"filter": {"entity": "Author"}, "project": "*", "sort": {"name": "asc"}})

    assert [row["name"] for row in rows] == ["Anna", "Boris"]
    assert all("age" not in row and "pen_name" not in row for row in rows)
    with pytest.raises(QueryValidationError, match="not visible"):
        service.query("library", {"filter": {"entity": "Author", "age": {"gte": 0}}, "project": ["name"]})


@pytest.mark.parametrize("actor", [None, {"role": "superuser"}], ids=["anonymous", "superuser"])
def test_query_policy_composes_with_acl_when_owner_and_group_are_resolved_and_excluded(query_services, actor):
    _entity_service, service, repo, ids = query_services
    denied_perm = {subject: {permission: False for permission in ("r", "w", "p")} for subject in ("owner", "group", "others")}
    repo.collection("library").update_many({"id": {"$in": [ids["book_alpha"], ids["author_boris"]]}}, {"$set": {"perm": denied_perm}})

    def before_query(context):
        context.exclude_fields("owner", "group", "perm")
        context.add_required_filter({"or": [
            {"entity": {"neq": "Book"}},
            {"pages": {"gte": 100}, "owner": "11111111-1111-4111-8111-111111111111"},
        ]})
        context.add_required_filter({"or": [{"entity": {"neq": "Author"}}, {"age": {"gte": 34}}]})

    service.hooks.register("before_query", before_query, module="library")
    rows = service.query(
        "library", {"filter": {"entity": "Book"}, "project": ["slug", "author.name", "owner.*", "group.*"]}, actor=actor
    )

    books = {row["slug"]: row for row in rows}
    assert set(books) == ({"alpha", "beta", "gamma", "delta"} if actor else {"beta", "gamma", "delta"})
    assert books["delta"]["author"] == {"name": "Anna"}
    assert books["gamma"].get("author") is None
    if actor:
        assert books["alpha"]["author"] == {"name": "Anna"}
        assert books["beta"]["author"] == {"name": "Boris"}
    else:
        assert books["beta"].get("author") is None
    assert all(not {"owner", "group", "perm"}.intersection(row) for row in rows)


def test_cross_module_policies_handle_mixed_targets_and_links_back_to_original_module(query_services):
    entity_service, service, repo, ids = query_services
    entity_service.create("people", "Author", author_schema())
    entity_service.create("people", "Person", author_schema())
    for name in ("anna", "boris", "clara"):
        author = repo.find_by_id("library", ids[f"author_{name}"])
        author["entity"] = "Person" if name == "boris" else "Author"
        repo.collection("people").insert_one(author)
    schema = book_schema(editor_entities=["Author", "Person"])
    schema["properties"]["author"]["x-meta"]["link"]["module"] = "people"
    schema["properties"]["editors"]["x-meta"]["link"]["module"] = "people"
    entity_service.update("library", "Book", schema)
    calls = []

    def people_policy(context):
        calls.append((context.module, context.path))
        context.add_required_filter({"age": {"gte": 34}})
        context.exclude_fields("age")

    def library_policy(context):
        calls.append((context.module, context.path))
        context.add_required_filter({"or": [{"entity": {"neq": "City"}}, {"zip": {"gte": 200000}}]})
        context.exclude_fields("zip")

    service.hooks.register("before_query", people_policy, module="people")
    service.hooks.register("before_query", library_policy, module="library")
    rows = service.query(
        "library",
        {"filter": {"entity": "Book", "slug": "alpha"}, "project": ["author.*", "author.city.*", "editors.*", "editors.city.*"]},
    )

    assert len(rows) == 1
    assert rows[0]["author"]["name"] == "Anna"
    assert rows[0]["author"].get("city") is None
    assert "age" not in rows[0]["author"]
    editors = {editor["name"]: editor for editor in rows[0]["editors"]}
    assert set(editors) == {"Anna", "Boris"}
    assert all("age" not in editor for editor in editors.values())
    assert editors["Boris"]["entity"] == "Person"
    assert editors["Boris"]["city"]["name"] == "Tula"
    assert "zip" not in editors["Boris"]["city"]
    assert calls == [
        ("library", ""),
        ("people", "author"),
        ("library", "author.city"),
        ("people", "editors"),
        ("library", "editors.city"),
    ]
    assert service.query("people", {"filter": {"entity": "Person"}, "project": ["name", "age"]}) == [{"name": "Boris"}]


@pytest.mark.parametrize("project", [None, ["*"]], ids=["default-project", "raw-project"])
def test_query_get_and_list_apply_policy_even_when_entity_is_excluded(query_services, project):
    _entity_service, service, _repo, ids = query_services

    def before_query(context):
        if not context.is_lookup:
            context.add_required_filter({"pages": {"gte": 150}})
            context.exclude_fields("entity", "pages", "owner", "group")

    service.hooks.register("before_query", before_query, module="library")
    project_options = {} if project is None else {"project": project}

    node = service.get("library", ids["book_gamma"], **project_options)
    assert node["slug"] == "gamma"
    assert not {"entity", "pages", "owner", "group"}.intersection(node)
    if project is None:
        assert node["author"]["name"] == "Clara"
    else:
        assert node["author"] == ids["author_clara"]
    with pytest.raises(NotFoundError):
        service.get("library", ids["book_alpha"], **project_options)

    rows = service.list_entity("library", "Book", {"filter": {"slug": "gamma"}, **project_options})
    assert [row["id"] for row in rows] == [ids["book_gamma"]]
    assert all(not {"entity", "pages", "owner", "group"}.intersection(row) for row in rows)
    assert service.list_entity("library", "Book", {"filter": {"slug": "alpha"}, **project_options}) == []
    rows = service.query("library", {"filter": {"entity": "Book", "slug": "gamma"}, **project_options})
    assert [row["id"] for row in rows] == [ids["book_gamma"]]
    assert all(not {"entity", "pages", "owner", "group"}.intersection(row) for row in rows)


@pytest.mark.parametrize("project", [None, ["slug"], ["*"]], ids=["default", "explicit", "raw"])
def test_get_runs_hooks_once_for_actual_query_and_allows_transforming_result_without_entity(query_services, project):
    _entity_service, service, repo, ids = query_services
    before_calls = []
    after_calls = []

    def before_query(context):
        before_calls.append((context.path, context.query))
        if not context.is_lookup:
            context.exclude_fields("entity")

    def after_query(context):
        after_calls.append((context.query, [row["slug"] for row in context.result]))
        context.result = [{"label": row["slug"].upper()} for row in context.result]

    service.hooks.register("before_query", before_query, module="library")
    service.hooks.register("after_query", after_query, module="library")
    expected_project = project if project is not None else service._build_default_read_project(
        service._entity_repo.get_schema("library", "Book")
    )
    expected_query = {"filter": {"id": ids["book_alpha"], "entity": "Book"}, "project": expected_project}

    result = service.get("library", ids["book_alpha"], project=project)

    assert result == {"label": "ALPHA"}
    assert [call for call in before_calls if not call[0]] == [("", expected_query)]
    assert after_calls == [(expected_query, ["alpha"])]
    assert [call[0] for call in before_calls] == (["", "author", "editors"] if project is None else [""])
    assert repo.find_by_id("library", ids["book_alpha"])["entity"] == "Book"


def test_get_does_not_bypass_query_policy_after_stored_acl_check(query_services):
    _entity_service, service, _repo, ids = query_services
    before_calls = []
    after_calls = []

    def before_query(context):
        before_calls.append(context.query)
        context.add_required_filter({"pages": {"gte": 150}})
        context.exclude_fields("entity")

    service.hooks.register("before_query", before_query, module="library")
    service.hooks.register("after_query", lambda context: after_calls.append(context.result), module="library")

    with pytest.raises(NotFoundError):
        service.get("library", ids["book_alpha"], project=["slug"])

    assert before_calls == [{
        "filter": {"id": ids["book_alpha"], "entity": "Book"}, "project": ["slug"],
    }]
    assert after_calls == [[]]


def test_after_query_receives_selected_page_and_can_transform_it_without_writing_nodes(query_services):
    _entity_service, service, repo, ids = query_services
    calls = []

    def after_query(context):
        calls.append([row["slug"] for row in context.result])
        context.result = [{"label": row["slug"].upper()} for row in reversed(context.result)]

    service.hooks.register("after_query", after_query, module="library")
    rows = service.query(
        "library", {"filter": {"entity": "Book"}, "project": ["slug"], "sort": {"slug": "asc"}, "offset": 1, "limit": 2}
    )

    assert calls == [["beta", "delta"]]
    assert rows == [{"label": "DELTA"}, {"label": "BETA"}]
    assert "label" not in repo.find_by_id("library", ids["book_beta"])


def test_query_hook_state_does_not_leak_between_concurrent_requests(query_services):
    _entity_service, service, _repo, _ids = query_services
    payload = {"filter": {"entity": "Book"}, "project": ["slug", "name"]}

    def before_query(context):
        context.add_required_filter({"slug": context.actor["user_id"]})
        context.query["sort"] = {"slug": "desc"}
        if context.actor["user_id"] == "alpha":
            context.exclude_fields("name")

    service.hooks.register("before_query", before_query, module="library")
    actors = [{"user_id": slug, "groups": []} for slug in ["alpha", "beta"] * 4]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda actor: service.query("library", payload, actor=actor), actors))

    assert results == [[{"slug": "alpha"}], [{"slug": "beta", "name": "Book Beta"}]] * 4
    assert payload == {"filter": {"entity": "Book"}, "project": ["slug", "name"]}
    assert [actor["user_id"] for actor in actors] == ["alpha", "beta"] * 4
