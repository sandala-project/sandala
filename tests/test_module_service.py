from __future__ import annotations

import copy

import pytest

from sandala.core.errors import AuthorizationError, ValidationError
from sandala.core.services.module_service import ModuleService

ADMIN_ACTOR = {"role": "admin"}
NONE_ROLE_ACTOR = {"role": "none"}
USER_ACTOR = {"role": "all"}
SUPERUSER_ACTOR = {
    "role": "superuser",
    "user_id": "11111111-1111-4111-8111-111111111111",
    "primary_group": "22222222-2222-4222-8222-222222222222",
}


class InMemoryModuleRepo:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def list_modules(self):
        return [copy.deepcopy(item) for item in self.docs.values()]

    def get_module(self, name):
        doc = self.docs.get(name)
        return copy.deepcopy(doc) if doc else None

    def module_exists(self, name):
        return name in self.docs

    def create_module(self, doc):
        self.docs[doc["name"]] = copy.deepcopy(doc)
        return copy.deepcopy(doc)

    def update_module(self, name, patch):
        if name not in self.docs:
            return None
        self.docs[name].update(copy.deepcopy(patch))
        return copy.deepcopy(self.docs[name])

    def delete_module(self, name):
        self.docs.pop(name, None)


class InMemoryEntityRepo:
    def __init__(self):
        self.modules: set[str] = set()
        self.entities: set[tuple[str, str]] = set()

    def module_exists(self, module):
        return module in self.modules

    def entity_exists(self, module, entity):
        return (module, entity) in self.entities


class InMemoryNodeRepo:
    def __init__(self):
        self.users = {
            "11111111-1111-4111-8111-111111111111": {"id": "11111111-1111-4111-8111-111111111111", "entity": "user", "deleted": False},
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa": {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "entity": "user", "deleted": False},
        }
        self.groups = {
            "22222222-2222-4222-8222-222222222222": {"id": "22222222-2222-4222-8222-222222222222", "entity": "group", "deleted": False},
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "entity": "group", "deleted": False},
        }
        self.active_count_by_module: dict[str, int] = {}
        self.indexed_modules: list[str] = []

    def ensure_module_indexes(self, module):
        self.indexed_modules.append(module)

    def find_one(self, module, query, projection=None):
        if module != "users":
            return None
        entity = query.get("entity")
        node_id = query.get("id")
        if query.get("deleted") is not False:
            return None
        if entity == "user":
            doc = self.users.get(node_id)
        elif entity == "group":
            doc = self.groups.get(node_id)
        else:
            doc = None
        return copy.deepcopy(doc) if doc else None

    def count_active_in_module(self, module):
        return self.active_count_by_module.get(module, 0)


def _service():
    return ModuleService(InMemoryModuleRepo(), InMemoryEntityRepo(), InMemoryNodeRepo())


def test_create_module_defaults_root_subjects_from_actor():
    svc = _service()
    created = svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )
    assert created["root_owner"] == SUPERUSER_ACTOR["user_id"]
    assert created["root_group"] == SUPERUSER_ACTOR["primary_group"]
    assert created["root_children_entities"] == []
    assert svc._node_repo.indexed_modules == ["library"]


def test_create_module_allows_empty_description():
    svc = _service()
    created = svc.create_module(
        {
            "name": "library",
            "description": "   ",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )
    assert created["description"] == ""


@pytest.mark.parametrize("operation", ["create", "patch"])
@pytest.mark.parametrize("invalid_role", ["extra", "owner", "group", "others"])
def test_module_rejects_invalid_root_perm_sections(operation, invalid_role):
    svc = _service()
    root_perm = {
        "owner": {"p": True},
        "group": {"p": True},
        "others": {"p": False},
    }
    payload = {
        "name": "library",
        "description": "Library",
        "root_children_entities": [],
        "root_perm": copy.deepcopy(root_perm),
    }
    if operation == "patch":
        svc.create_module(payload, actor=SUPERUSER_ACTOR)

    invalid_root_perm = copy.deepcopy(root_perm)
    if invalid_role == "extra":
        invalid_root_perm["extra"] = {"p": True}
    else:
        invalid_root_perm.pop(invalid_role)

    with pytest.raises(ValidationError, match="must contain exactly"):
        if operation == "create":
            svc.create_module({**payload, "root_perm": invalid_root_perm}, actor=SUPERUSER_ACTOR)
        else:
            svc.patch_module("library", {"root_perm": invalid_root_perm}, actor=SUPERUSER_ACTOR)

    if operation == "create":
        assert svc._module_repo.get_module("library") is None
        assert svc._node_repo.indexed_modules == []
    else:
        assert svc.get_module("library", actor=SUPERUSER_ACTOR)["root_perm"] == root_perm


def test_list_and_get_module_require_admin_or_superuser():
    svc = _service()
    svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )

    assert svc.list_modules(actor=ADMIN_ACTOR)[0]["name"] == "library"
    assert svc.get_module("library", actor=ADMIN_ACTOR)["name"] == "library"

    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.list_modules(actor=USER_ACTOR)
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.get_module("library", actor=USER_ACTOR)
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.list_modules(actor=NONE_ROLE_ACTOR)
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.get_module("library", actor=NONE_ROLE_ACTOR)


def test_create_module_allows_explicit_root_subjects():
    svc = _service()
    created = svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_owner": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "root_group": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )
    assert created["root_owner"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert created["root_group"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_patch_module_rejects_unknown_root_owner():
    svc = _service()
    svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )
    with pytest.raises(ValidationError, match="root_owner"):
        svc.patch_module(
            "library",
            {"root_owner": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"},
            actor=SUPERUSER_ACTOR,
        )


def test_create_module_rejects_missing_root_children_entities():
    svc = _service()

    with pytest.raises(ValidationError, match="root_children_entities"):
        svc.create_module(
            {
                "name": "library",
                "description": "Library",
                "root_perm": {
                    "owner": {"p": True},
                    "group": {"p": True},
                    "others": {"p": False},
                },
            },
            actor=SUPERUSER_ACTOR,
        )


def test_create_module_rejects_non_empty_root_children_entities():
    svc = _service()
    svc._entity_repo.entities.add(("library", "Book"))

    with pytest.raises(ValidationError, match="must be an empty array"):
        svc.create_module(
            {
                "name": "library",
                "description": "Library",
                "root_children_entities": ["Book"],
                "root_perm": {
                    "owner": {"p": True},
                    "group": {"p": True},
                    "others": {"p": False},
                },
            },
            actor=SUPERUSER_ACTOR,
        )


def test_patch_module_validates_root_children_entities_against_existing_entities():
    svc = _service()
    svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )
    svc._entity_repo.entities.update({("library", "Book"), ("library", "Author")})

    updated = svc.patch_module(
        "library",
        {"root_children_entities": ["Book", "Author", "Book"]},
        actor=SUPERUSER_ACTOR,
    )

    assert updated["root_children_entities"] == ["Book", "Author"]


def test_patch_module_allows_empty_description():
    svc = _service()
    svc.create_module(
        {
            "name": "library",
            "description": "Library",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        },
        actor=SUPERUSER_ACTOR,
    )

    updated = svc.patch_module(
        "library",
        {"description": "   "},
        actor=SUPERUSER_ACTOR,
    )

    assert updated["description"] == ""
