from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from tests.integration.helpers import mongo_services
from tests.integration.query_dataset import seed_query_dataset


@pytest.mark.integration
def test_query_project_hides_aux_filter_and_sort_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug"],
                "filter": {
                    "entity": "Book",
                    "author.city.name": "Kazan",
                    "editors.city.name": {"in": ["Moscow", "Kazan"]},
                },
                "sort": {"author.age": "desc", "editors.city.zip": "asc"},
            },
        )

        assert rows == [{"name": "Book Gamma", "slug": "gamma"}]
        assert "author" not in rows[0]


@pytest.mark.integration
def test_query_project_star_with_resolved_paths_excludes_mongo_id():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["*", "author.name", "author.city.name", "editors.name", "editors.city.name"],
                "filter": {"entity": "Book", "id": ids["book_alpha"]},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert "_id" not in row
        assert row["id"] == ids["book_alpha"]
        assert row["entity"] == "Book"
        assert row["deleted"] is False
        assert row["name"] == "Book Alpha"
        assert row["slug"] == "alpha"
        assert row["author"]["name"] == "Anna"
        assert row["author"]["city"]["name"] == "Moscow"
        assert "_id" not in row["author"]
        assert "_id" not in row["author"]["city"]
        assert len(row["editors"]) == 2
        assert all("_id" not in editor for editor in row["editors"])
        assert all("_id" not in editor["city"] for editor in row["editors"])


@pytest.mark.integration
def test_query_project_wildcard_and_deep_path_for_linkarray():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "editors.*", "editors.city.name"],
                "filter": {"entity": "Book", "id": ids["book_alpha"]},
            },
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Book Alpha"
        assert row["slug"] == "alpha"
        assert len(row["editors"]) == 2

        editor_names = sorted(editor["name"] for editor in row["editors"])
        assert editor_names == ["Anna", "Boris"]

        anna = next(editor for editor in row["editors"] if editor["name"] == "Anna")
        boris = next(editor for editor in row["editors"] if editor["name"] == "Boris")
        assert anna["entity"] == "Author"
        assert anna["id"] == ids["author_anna"]
        assert anna["city"]["name"] == "Moscow"
        assert boris["entity"] == "Author"
        assert boris["id"] == ids["author_boris"]
        assert boris["city"]["name"] == "Tula"


@pytest.mark.integration
def test_query_linkarray_skips_deleted_and_missing_link_targets():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "editors.*"],
                "filter": {"entity": "Book", "id": ids["book_alpha"]},
            },
        )

        assert len(rows) == 1
        editors = rows[0]["editors"]
        assert len(editors) == 2
        assert sorted(editor["id"] for editor in editors) == [ids["author_anna"], ids["author_boris"]]
        assert ids["author_deleted"] not in {editor["id"] for editor in editors}
        assert ids["author_missing"] not in {editor["id"] for editor in editors}
        assert all(editor["deleted"] is False for editor in editors)
        assert all(editor["entity"] == "Author" for editor in editors)


@pytest.mark.integration
def test_query_linkarray_skips_acl_denied_link_targets():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["author_boris"]},
            {"$set": {"perm.others.r": False}},
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "editors.*"],
                "filter": {"entity": "Book", "id": ids["book_alpha"]},
            },
        )

        assert len(rows) == 1
        editors = rows[0]["editors"]
        assert len(editors) == 1
        assert editors[0]["id"] == ids["author_anna"]


@pytest.mark.integration
def test_list_entity_rejects_conflicting_entity_filter_with_empty_result():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo, include_magazine=True)

        rows = node_service.list_entity(
            "library",
            "Book",
            {
                "project": ["name"],
                "filter": {"entity": "Magazine"},
            },
        )

        assert rows == []


@pytest.mark.integration
def test_list_entity_intersects_user_filter_with_required_entity():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo, include_magazine=True)

        rows = node_service.list_entity(
            "library",
            "Book",
            {
                "project": ["name", "slug", "pages"],
                "filter": {"pages": {"gte": 150}},
                "sort": {"slug": "asc"},
            },
        )

        assert [(row["slug"], row["pages"]) for row in rows] == [
            ("beta", 220),
            ("delta", 150),
            ("gamma", 150),
        ]


@pytest.mark.integration
def test_list_entity_default_project_resolves_schema_links_owner_and_group_only():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        root_user = node_repo.find_one("users", {"entity": "user", "username": "admin", "deleted": False})
        default_group = node_repo.find_one("users", {"entity": "group", "groupname": "default", "deleted": False})
        assert root_user is not None
        assert default_group is not None
        node_repo.collection("library").update_one(
            {"id": ids["book_alpha"]},
            {
                "$set": {
                    "parent": ids["author_anna"],
                    "ancestors": [ids["author_anna"]],
                    "owner": root_user["id"],
                    "group": default_group["id"],
                }
            },
        )

        rows = node_service.list_entity(
            "library",
            "Book",
            {"filter": {"id": ids["book_alpha"]}},
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["author"]["name"] == "Anna"
        assert row["owner"]["username"] == "admin"
        assert row["group"]["groupname"] == "default"
        assert row["parent"] == ids["author_anna"]
        assert row["ancestors"] == [ids["author_anna"]]


@pytest.mark.integration
def test_query_field_collision_fails_without_entity_scope_and_passes_with_scope():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo, include_magazine=True)

        with pytest.raises(ValidationError, match="Field collision"):
            node_service.query(
                "library",
                {
                    "project": ["author.name"],
                    "sort": {"author.name": "asc"},
                },
            )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "author.name"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["alpha", "beta", "delta", "gamma"]
        assert rows[0]["author"]["name"] == "Anna"
        assert rows[1]["author"]["name"] == "Boris"
        assert rows[3]["author"]["name"] == "Clara"


@pytest.mark.integration
def test_query_invalid_payloads_raise_validation_errors():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        with pytest.raises(ValidationError, match="filter must be an object"):
            node_service.query("library", {"project": ["name"], "filter": []})

        with pytest.raises(ValidationError, match="must be 'asc' or 'desc'"):
            node_service.query("library", {"project": ["name"], "sort": {"name": "up"}})

        with pytest.raises(ValidationError, match="Logical operator 'and'"):
            node_service.query("library", {"project": ["name"], "filter": {"and": []}})

        with pytest.raises(ValidationError, match="Unsupported filter operator"):
            node_service.query("library", {"project": ["name"], "filter": {"name": {"foo": 1}}})

        with pytest.raises(ValidationError, match="empty operator object"):
            node_service.query("library", {"project": ["name"], "filter": {"name": {}}})

        with pytest.raises(ValidationError, match="limit must be positive integer"):
            node_service.query("library", {"project": ["name"], "limit": 0})
