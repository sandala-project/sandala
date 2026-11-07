from __future__ import annotations

import pytest

from tests.integration.helpers import mongo_services
from tests.integration.query_dataset import seed_query_dataset


@pytest.mark.integration
def test_query_sort_by_root_field_ascending_and_descending():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        asc_rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
            },
        )
        desc_rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "rating"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "desc"},
            },
        )

        assert [row["slug"] for row in asc_rows] == ["alpha", "beta", "delta", "gamma"]
        assert [row["slug"] for row in desc_rows] == ["gamma", "delta", "beta", "alpha"]
        assert asc_rows[0]["name"] == "Book Alpha"
        assert desc_rows[0]["name"] == "Book Gamma"


@pytest.mark.integration
def test_query_sort_by_resolved_author_and_city_fields():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "author.name", "author.city.name", "author.city.zip"],
                "filter": {"entity": "Book"},
                "sort": {"author.city.zip": "asc", "slug": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["alpha", "delta", "beta", "gamma"]
        assert rows[0]["author"] == {"name": "Anna", "city": {"name": "Moscow", "zip": 101000}}
        assert rows[2]["author"] == {"name": "Boris", "city": {"name": "Tula", "zip": 300000}}
        assert rows[3]["author"] == {"name": "Clara", "city": {"name": "Kazan", "zip": 420000}}


@pytest.mark.integration
def test_query_multisort_with_tie_breaker_is_stable():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["id", "name", "slug", "rating", "pages"],
                "filter": {"entity": "Book"},
                "sort": {"rating": "desc", "id": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["alpha", "gamma", "delta", "beta"]
        assert rows[1]["rating"] == 4.2 and rows[2]["rating"] == 4.2
        assert rows[1]["id"] == ids["book_gamma"]
        assert rows[2]["id"] == ids["book_delta"]
        assert rows[0]["pages"] == 100
        assert rows[-1]["pages"] == 220


@pytest.mark.integration
def test_query_sort_with_null_and_missing_values_and_projection():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "subtitle", "author.name"],
                "filter": {"entity": "Book"},
                "sort": {"subtitle": "asc", "slug": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["beta", "gamma", "alpha", "delta"]
        assert rows[0]["subtitle"] is None
        assert "subtitle" not in rows[1]
        assert rows[2]["subtitle"] == "First"
        assert rows[3]["subtitle"] == "Tie"
        assert rows[0]["author"]["name"] == "Boris"
        assert rows[1]["author"]["name"] == "Clara"


@pytest.mark.integration
def test_query_limit_offset_with_stable_sorted_page():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug", "pages", "author.name", "author.city.name"],
                "filter": {"entity": "Book"},
                "sort": {"pages": "asc", "slug": "asc"},
                "offset": 1,
                "limit": 2,
            },
        )

        assert [row["slug"] for row in rows] == ["delta", "gamma"]
        assert rows[0]["pages"] == 150 and rows[1]["pages"] == 150
        assert rows[0]["author"] == {"name": "Anna", "city": {"name": "Moscow"}}
        assert rows[1]["author"] == {"name": "Clara", "city": {"name": "Kazan"}}


@pytest.mark.integration
def test_query_limit_and_offset_beyond_range_behavior():
    with mongo_services() as (entity_service, node_service, node_repo):
        seed_query_dataset(entity_service, node_repo)

        limited_rows = node_service.query(
            "library",
            {
                "project": ["name", "slug"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
                "limit": 1,
            },
        )
        offset_rows = node_service.query(
            "library",
            {
                "project": ["name", "slug"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
                "offset": 100,
            },
        )

        assert limited_rows == [{"name": "Book Alpha", "slug": "alpha"}]
        assert offset_rows == []


@pytest.mark.integration
def test_query_sort_respects_acl_visibility_of_root_nodes():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = seed_query_dataset(entity_service, node_repo)
        node_repo.collection("library").update_one(
            {"id": ids["book_beta"]},
            {"$set": {"perm.others.r": False}},
        )

        rows = node_service.query(
            "library",
            {
                "project": ["name", "slug"],
                "filter": {"entity": "Book"},
                "sort": {"slug": "asc"},
            },
        )

        assert [row["slug"] for row in rows] == ["alpha", "delta", "gamma"]
