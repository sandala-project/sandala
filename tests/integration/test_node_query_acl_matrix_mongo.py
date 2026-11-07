from __future__ import annotations

import pytest

from sandala.core.errors import ValidationError
from sandala.core.time_utils import utc_now_iso
from tests.integration.helpers import mongo_services


@pytest.mark.integration
def test_owner_branch_has_priority_over_group_and_others():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {"project": ["id", "name"], "filter": {"entity": "Doc", "id": ids["doc_owner_denied"]}},
            actor={"user_id": ids["actor_owner"], "groups": [ids["group_actor"]]},
        )
        assert rows == []


@pytest.mark.integration
def test_group_branch_allows_when_owner_not_matched():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {"project": ["id", "name"], "filter": {"entity": "Doc", "id": ids["doc_group_allowed"]}},
            actor={"user_id": ids["actor_other"], "groups": [ids["group_actor"]]},
        )
        assert len(rows) == 1
        assert rows[0]["id"] == ids["doc_group_allowed"]


@pytest.mark.integration
def test_default_get_and_list_keep_owner_and_group_acl_after_owner_and_group_resolution():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)
        actor = {"user_id": ids["actor_owner"], "groups": [ids["group_actor"]]}

        node = node_service.get("library", ids["doc_owner_allowed"], actor=actor)
        assert node["id"] == ids["doc_owner_allowed"]

        rows = node_service.list_entity(
            "library",
            "Doc",
            {"filter": {"id": ids["doc_owner_allowed"]}},
            actor=actor,
        )
        assert [row["id"] for row in rows] == [ids["doc_owner_allowed"]]

        group_actor = {"user_id": ids["actor_other"], "groups": [ids["group_actor"]]}
        node = node_service.get("library", ids["doc_group_allowed"], actor=group_actor)
        assert node["id"] == ids["doc_group_allowed"]

        rows = node_service.list_entity(
            "library",
            "Doc",
            {"filter": {"id": ids["doc_group_allowed"]}},
            actor=group_actor,
        )
        assert [row["id"] for row in rows] == [ids["doc_group_allowed"]]


@pytest.mark.integration
def test_others_branch_allows_for_unauthenticated_actor():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {"project": ["id", "name"], "filter": {"entity": "Doc", "id": ids["doc_others_allowed"]}},
        )
        assert len(rows) == 1
        assert rows[0]["id"] == ids["doc_others_allowed"]


@pytest.mark.integration
def test_all_false_denies_access():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {"project": ["id", "name"], "filter": {"entity": "Doc", "id": ids["doc_all_denied"]}},
            actor={"user_id": ids["actor_other"], "groups": [ids["group_other"]]},
        )
        assert rows == []


@pytest.mark.integration
def test_superuser_bypasses_acl():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {"project": ["id", "name"], "filter": {"entity": "Doc", "id": ids["doc_all_denied"]}},
            actor={"role": "superuser"},
        )
        assert len(rows) == 1
        assert rows[0]["id"] == ids["doc_all_denied"]


@pytest.mark.integration
def test_lookup_applies_acl_to_linked_nodes():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["id", "author.name"],
                "filter": {"entity": "Doc", "id": ids["doc_with_denied_author"]},
            },
            actor={"user_id": ids["actor_other"], "groups": [ids["group_other"]]},
        )
        assert len(rows) == 1
        assert rows[0]["id"] == ids["doc_with_denied_author"]
        assert rows[0].get("author") is None


@pytest.mark.integration
def test_final_match_applies_acl_when_no_lookup():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["id", "name"],
                "filter": {"entity": "Doc"},
                "sort": {"name": "asc"},
                "offset": 0,
                "limit": 50,
            },
            actor={"user_id": ids["actor_other"], "groups": [ids["group_other"]]},
        )
        returned_ids = {row["id"] for row in rows}
        assert ids["doc_all_denied"] not in returned_ids
        assert ids["doc_group_allowed"] not in returned_ids
        assert ids["doc_owner_denied"] in returned_ids


@pytest.mark.integration
def test_filter_on_deleted_is_rejected_for_all_roles_and_perm_for_non_superuser():
    with mongo_services() as (entity_service, node_service, node_repo):
        _seed_acl_matrix_dataset(entity_service, node_repo)

        with pytest.raises(ValidationError, match="deleted field"):
            node_service.query("library", {"project": ["name"], "filter": {"deleted": False}})
        with pytest.raises(ValidationError, match="ACL fields"):
            node_service.query("library", {"project": ["name"], "filter": {"perm.others.r": True}})
        with pytest.raises(ValidationError, match="deleted field"):
            node_service.query(
                "library",
                {"project": ["name"], "filter": {"deleted": False}},
                actor={"role": "superuser"},
            )


@pytest.mark.integration
def test_superuser_filter_on_perm_is_allowed():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)

        rows = node_service.query(
            "library",
            {
                "project": ["id", "name"],
                "filter": {"entity": "Doc", "perm.others.r": False},
                "sort": {"name": "asc"},
            },
            actor={"role": "superuser"},
        )
        returned_ids = {row["id"] for row in rows}
        assert ids["doc_owner_denied"] not in returned_ids
        assert ids["doc_all_denied"] in returned_ids
        assert ids["doc_group_allowed"] in returned_ids


@pytest.mark.integration
def test_superuser_excludes_deleted_root_and_linked_nodes():
    with mongo_services() as (entity_service, node_service, node_repo):
        ids = _seed_acl_matrix_dataset(entity_service, node_repo)
        node_repo.collection("library").update_many(
            {"id": {"$in": [ids["author_denied"], ids["doc_all_denied"]]}},
            {"$set": {"deleted": True}},
        )

        rows = node_service.query(
            "library",
            {
                "project": ["id", "author.name"],
                "filter": {"entity": "Doc"},
            },
            actor={"role": "superuser"},
        )

        assert ids["doc_all_denied"] not in {row["id"] for row in rows}
        assert all("author" not in row for row in rows)


def _seed_acl_matrix_dataset(entity_service, node_repo) -> dict[str, str]:
    entity_service.create("library", "Author", _author_schema())
    entity_service.create("library", "Doc", _doc_schema())

    now = utc_now_iso()
    ids = {
        "actor_owner": "70000000-0000-4700-8700-000000000001",
        "actor_other": "70000000-0000-4700-8700-000000000002",
        "group_actor": "70000000-0000-4700-8700-000000001001",
        "group_other": "70000000-0000-4700-8700-000000001002",
        "author_denied": "70000000-0000-4700-8700-000000002001",
        "doc_owner_denied": "70000000-0000-4700-8700-000000003001",
        "doc_owner_allowed": "70000000-0000-4700-8700-000000003006",
        "doc_group_allowed": "70000000-0000-4700-8700-000000003002",
        "doc_others_allowed": "70000000-0000-4700-8700-000000003003",
        "doc_all_denied": "70000000-0000-4700-8700-000000003004",
        "doc_with_denied_author": "70000000-0000-4700-8700-000000003005",
    }

    node_repo.collection("library").insert_many(
        [
            _node(
                ids["author_denied"],
                "Author",
                now,
                owner=ids["actor_owner"],
                group=ids["group_actor"],
                perm=_perm(owner=False, group=False, others=False),
                name="Hidden Author",
            ),
            _node(
                ids["doc_owner_denied"],
                "Doc",
                now,
                owner=ids["actor_owner"],
                group=ids["group_actor"],
                perm=_perm(owner=False, group=True, others=True),
                name="Owner Denied",
                author=ids["author_denied"],
            ),
            _node(
                ids["doc_owner_allowed"],
                "Doc",
                now,
                owner=ids["actor_owner"],
                group=ids["group_actor"],
                perm=_perm(owner=True, group=False, others=False),
                name="Owner Allowed",
                author=ids["author_denied"],
            ),
            _node(
                ids["doc_group_allowed"],
                "Doc",
                now,
                owner="70000000-0000-4700-8700-000000000099",
                group=ids["group_actor"],
                perm=_perm(owner=False, group=True, others=False),
                name="Group Allowed",
                author=ids["author_denied"],
            ),
            _node(
                ids["doc_others_allowed"],
                "Doc",
                now,
                owner="70000000-0000-4700-8700-000000000098",
                group=ids["group_other"],
                perm=_perm(owner=False, group=False, others=True),
                name="Others Allowed",
                author=ids["author_denied"],
            ),
            _node(
                ids["doc_all_denied"],
                "Doc",
                now,
                owner="70000000-0000-4700-8700-000000000097",
                group=ids["group_other"],
                perm=_perm(owner=False, group=False, others=False),
                name="All Denied",
                author=ids["author_denied"],
            ),
            _node(
                ids["doc_with_denied_author"],
                "Doc",
                now,
                owner="70000000-0000-4700-8700-000000000096",
                group=ids["group_other"],
                perm=_perm(owner=False, group=True, others=True),
                name="Denied Linked Author",
                author=ids["author_denied"],
            ),
        ]
    )
    return ids


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


def _doc_schema() -> dict:
    return {
        "title": "Doc",
        "description": "Doc",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
            "author": {
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
        "required": ["name", "author"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": {"owner": {"r": True, "w": True, "p": True}, "group": {"r": False, "w": False, "p": False}, "others": {"r": False, "w": False, "p": False}}}},
    }


def _perm(*, owner: bool, group: bool, others: bool) -> dict:
    return {
        "owner": {"r": owner, "w": owner, "p": owner},
        "group": {"r": group, "w": group, "p": group},
        "others": {"r": others, "w": others, "p": others},
    }


def _node(node_id: str, entity: str, now: str, *, owner: str, group: str, perm: dict, deleted: bool = False, **fields):
    return {
        "id": node_id,
        "entity": entity,
        "parent": None,
        "owner": owner,
        "group": group,
        "perm": perm,
        "depth": 0,
        "ancestors": [],
        "deleted": deleted,
        "cdate": now,
        "mdate": now,
        **fields,
    }
