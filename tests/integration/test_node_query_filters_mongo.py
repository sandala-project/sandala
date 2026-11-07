from __future__ import annotations

import pytest

from tests.integration.helpers import mongo_services
from tests.integration.query_dataset import seed_query_dataset


@pytest.mark.integration
def test_query_filter_eq_on_root_field_returns_full_book_object():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating", "subtitle", "author.*", "author.city.*", "editors.*"],
                "filter": {"entity": "Book", "slug": "alpha"},
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book Alpha"
        assert book["slug"] == "alpha"
        assert book["pages"] == 100
        assert book["rating"] == 4.7
        assert book["subtitle"] == "First"
        assert book["author"]["name"] == "Anna"
        assert book["author"]["age"] == 34
        assert book["author"]["city"]["name"] == "Moscow"
        assert book["author"]["city"]["zip"] == 101000
        assert sorted(editor["name"] for editor in book["editors"]) == ["Anna", "Boris"]


@pytest.mark.integration
def test_query_filter_range_and_inclusion_operators_on_root_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating"],
                "filter": {
                    "entity": "Book",
                    "pages": {"gte": 120, "lte": 220},
                    "slug": {"in": ["beta", "gamma", "delta"], "nin": ["delta"]},
                },
                "sort": {"slug": "asc"},
            },
        )

        assert [item["slug"] for item in rows] == ["beta", "gamma"]
        assert rows[0] == {"name": "Book Beta", "slug": "beta", "pages": 220, "rating": 3.9}
        assert rows[1] == {"name": "Book Gamma", "slug": "gamma", "pages": 150, "rating": 4.2}


@pytest.mark.integration
def test_query_filter_regex_exists_and_size_on_mixed_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "subtitle", "editors"],
                "filter": {
                    "entity": "Book",
                    "name": {"regex": "^Book (Alpha|Gamma)$"},
                    "subtitle": {"exists": False},
                    "editors": {"size": 2},
                },
            },
        )

        assert len(rows) == 1
        assert rows[0]["name"] == "Book Gamma"
        assert rows[0]["slug"] == "gamma"
        assert "subtitle" not in rows[0]
        assert len(rows[0]["editors"]) == 2


@pytest.mark.integration
def test_query_filter_nested_and_or_not_combination_returns_expected_subset():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating", "editors.name", "editors.city.name"],
                "filter": {
                    "and": [
                        {"entity": "Book"},
                        {
                            "or": [
                                {"pages": {"gte": 150}},
                                {"editors.city.zip": {"eq": 101000}},
                            ]
                        },
                        {"not": [{"editors.city.name": {"eq": "Tula"}}]},
                    ]
                },
                "sort": {"slug": "asc"},
            },
        )

        assert [item["slug"] for item in rows] == ["delta", "gamma"]
        assert rows[0]["pages"] == 150 and rows[0]["rating"] == 4.2
        assert rows[0]["editors"] == []
        assert rows[1]["pages"] == 150 and rows[1]["rating"] == 4.2
        assert sorted(editor["name"] for editor in rows[1]["editors"]) == ["Anna", "Clara"]


@pytest.mark.integration
def test_query_filter_by_resolved_author_city_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "author.*", "author.city.*"],
                "filter": {
                    "entity": "Book",
                    "author.city.name": "Tula",
                    "author.city.zip": {"eq": 300000},
                },
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["name"] == "Book Beta"
        assert book["slug"] == "beta"
        assert book["author"]["name"] == "Boris"
        assert book["author"]["age"] == 41
        assert book["author"]["city"]["name"] == "Tula"
        assert book["author"]["city"]["zip"] == 300000
        assert book["author"]["city"]["entity"] == "City"
        assert book["author"]["city"]["deleted"] is False


@pytest.mark.integration
def test_query_filter_by_resolved_editors_nested_city_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "editors.*", "editors.city.*"],
                "filter": {
                    "entity": "Book",
                    "editors.city.zip": {"gte": 400000},
                    "editors.age": {"gte": 29},
                    "editors.city.name": {"regex": "^Kaz"},
                },
            },
        )

        assert len(rows) == 1
        book = rows[0]
        assert book["slug"] == "gamma"
        assert book["name"] == "Book Gamma"
        by_name = {editor["name"]: editor["city"]["zip"] for editor in book["editors"]}
        assert by_name == {"Anna": 101000, "Clara": 420000}


@pytest.mark.integration
def test_query_filter_combines_root_and_resolved_predicates():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "author.name", "author.city.name"],
                "filter": {
                    "entity": "Book",
                    "pages": 150,
                    "author.city.name": {"in": ["Moscow", "Kazan"]},
                },
                "sort": {"slug": "asc"},
            },
        )

        assert [item["slug"] for item in rows] == ["delta", "gamma"]
        assert rows[0]["author"] == {"name": "Anna", "city": {"name": "Moscow"}}
        assert rows[1]["author"] == {"name": "Clara", "city": {"name": "Kazan"}}
        assert all(item["pages"] == 150 for item in rows)


@pytest.mark.integration
def test_query_deleted_nodes_are_excluded_even_when_filter_matches():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating"],
                "filter": {
                    "entity": "Book",
                    "slug": "deleted",
                },
            },
        )

        assert rows == []
