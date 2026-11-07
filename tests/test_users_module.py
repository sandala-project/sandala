from __future__ import annotations

from typing import Any

import pytest

from sandala.core.errors import (
    AnonymousRegistrationDisabledError,
    AuthorizationError,
    DefaultGroupDeletionForbiddenError,
    DefaultGroupNotFoundError,
    EmailAlreadyExistsError,
    EmailInvalidError,
    IdentityInUseError,
    PasswordHashDirectWriteForbiddenError,
    RoleAssignmentForbiddenError,
    SelfDeletionForbiddenError,
    LastSuperuserDeletionForbiddenError,
    UsernameAlreadyExistsError,
    UserGroupNotFoundError,
    ValidationError,
)
from sandala.core.services.node_hooks import NodeHookContext
from sandala.core.security import SecurityService
from sandala.core.users.bootstrap import ensure_users_module
from sandala.core.users.hooks import UsersGroupNodeHooks, UsersUserNodeHooks
from sandala.core.users.schemas import group_schema, user_schema


class StubSecurity:
    def __init__(self):
        self._security = SecurityService()

    def normalize_username(self, value: Any, *, field_name: str = "username") -> str:
        return self._security.normalize_username(value, field_name=field_name)

    def hash_password(self, raw_password: str) -> str:
        return f"hash:{raw_password}"


class InMemoryCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None):
        self.docs = [dict(item) for item in (docs or [])]

    def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        for doc in self.docs:
            if _matches(doc, query):
                result = dict(doc)
                if projection:
                    result.pop("_id", None)
                    if projection.get("password_hash") == 0:
                        result.pop("password_hash", None)
                return result
        return None

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(dict(doc))


class InMemoryNodeRepo:
    def __init__(self, users_docs: list[dict[str, Any]] | None = None):
        self.users_collection = InMemoryCollection(users_docs)
        self.indexed_modules: list[str] = []

    def ensure_module_indexes(self, module: str) -> None:
        self.indexed_modules.append(module)

    def collection(self, module: str) -> InMemoryCollection:
        assert module == "users"
        return self.users_collection

    def find_one(self, module: str, query: dict[str, Any], projection: dict[str, Any] | None = None):
        return self.collection(module).find_one(query, projection)

    def insert_node(self, module: str, node: dict[str, Any]) -> dict[str, Any]:
        self.collection(module).insert_one(node)
        return dict(node)


class StubEntityService:
    def __init__(self, existing: set[tuple[str, str]] | None = None):
        self.existing = set(existing or set())
        self.created: list[tuple[str, str]] = []
        self.schemas: dict[tuple[str, str], dict[str, Any]] = {}

    def entity_exists(self, module: str, entity: str) -> bool:
        return (module, entity) in self.existing

    def create(self, module: str, entity: str, schema: dict[str, Any]):
        self.existing.add((module, entity))
        self.created.append((module, entity))
        self.schemas[(module, entity)] = schema

    def get_schema(self, module: str, entity: str) -> dict[str, Any] | None:
        return self.schemas.get((module, entity))


class StubModuleRepo:
    def __init__(self):
        self.modules: set[str] = set()
        self.docs: dict[str, dict[str, Any]] = {}

    def module_exists(self, name: str) -> bool:
        return name in self.modules

    def create_module(self, doc: dict[str, Any]):
        self.modules.add(doc["name"])
        self.docs[doc["name"]] = dict(doc)
        return dict(doc)

    def list_modules(self) -> list[dict[str, Any]]:
        return [dict(self.docs[name]) for name in sorted(self.docs)]


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(doc, item) for item in value):
                return False
            continue
        if key == "$nor":
            if any(_matches(doc, item) for item in value):
                return False
            continue
        doc_value = doc.get(key)
        if isinstance(value, dict) and "$ne" in value:
            if doc_value == value["$ne"]:
                return False
            continue
        if isinstance(value, dict) and "$in" in value:
            if doc_value not in value["$in"]:
                return False
            continue
        if isinstance(doc_value, list):
            if value not in doc_value:
                return False
            continue
        if doc_value != value:
            return False
    return True


def test_user_before_create_normalizes_and_hashes_password():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u1",
        "username": " Alice ",
        "email": "TeSt@пример.рф",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }
    context = NodeHookContext(
        event="before_create",
        module="users",
        entity="user",
        payload=payload,
        actor={"user_id": "root", "primary_group": "g-default", "groups": ["g-default"], "role": "superuser"},
    )

    hooks.before_create(context)

    assert payload["username"] == "alice"
    assert payload["email"] == "test@xn--e1afmkfd.xn--p1ai"
    assert payload["password_hash"] == "hash:Abcd1234!"
    assert payload["password"] == "Abcd1234!"
    assert payload["role"] == "all"
    assert payload["active"] is True


def test_user_before_create_allows_absent_password_without_hash():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u1",
        "username": "alice",
        "groups": [],
    }

    hooks.before_create(
        NodeHookContext(
            event="before_create",
            module="users",
            entity="user",
            payload=payload,
            actor={"user_id": "root", "primary_group": "g-default", "groups": ["g-default"], "role": "superuser"},
        )
    )

    assert "password" not in payload
    assert "password_hash" not in payload


@pytest.mark.parametrize("password", [None, ""])
def test_user_before_create_rejects_present_empty_password(password: str | None):
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(ValidationError, match="password.*non-empty string") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={"id": "u1", "username": "alice", "password": password, "groups": []},
                actor={"user_id": "root", "primary_group": "g-default", "groups": ["g-default"], "role": "superuser"},
            )
        )

    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["password"],
                "message": "Password must be a non-empty string",
                "keyword": "password_invalid",
            }
        ]
    }


def test_user_before_create_attaches_username_field_error():
    hooks = UsersUserNodeHooks(InMemoryNodeRepo(), StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(ValidationError, match="username.*non-empty string") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={"id": "u1", "username": None, "groups": []},
                actor={"user_id": "root", "role": "superuser"},
            )
        )

    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["username"],
                "message": "Field 'username' must be a non-empty string",
                "keyword": "username_invalid",
            }
        ]
    }


def test_user_before_create_does_not_enforce_schema_policy():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})

    payload = {
        "id": "u1",
        "username": " John Doe ",
        "password": "Abcd1234!",
        "groups": [],
    }
    hooks.before_create(
        NodeHookContext(
            event="before_create",
            module="users",
            entity="user",
            payload=payload,
            actor={"user_id": "root", "primary_group": "g-default", "groups": ["g-default"], "role": "superuser"},
        )
    )
    assert payload["username"] == "john doe"


def test_user_before_create_assigns_default_group_when_primary_group_missing():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u1",
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }

    hooks.before_create(
        NodeHookContext(
            event="before_create",
            module="users",
            entity="user",
            payload=payload,
            actor={"user_id": "root", "primary_group": "root-group", "role": "superuser"},
        )
    )

    assert payload["primary_group"] == "g-default"
    assert payload["groups"] == ["g-default"]


def test_user_before_create_sets_owner_group_and_actor_to_created_user():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(
        node_repo,
        StubModuleRepo(),
        StubSecurity(),
        {"ALLOW_ANONYMOUS_USER_REGISTRATION": True},
    )
    payload = {
        "id": "u-new",
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }
    context = NodeHookContext(
        event="before_create",
        module="users",
        entity="user",
        payload=payload,
        actor=None,
    )

    hooks.before_create(context)

    assert payload["owner"] == "u-new"
    assert payload["group"] == payload["primary_group"]
    assert context.actor == {
        "user_id": "u-new",
        "primary_group": payload["primary_group"],
        "groups": payload["groups"],
        "role": payload["role"],
    }


def test_user_before_create_rejects_anonymous_when_registration_disabled():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u-new",
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }

    with pytest.raises(AnonymousRegistrationDisabledError, match="Anonymous user registration is disabled") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload=payload,
                actor=None,
            )
        )
    assert exc_info.value.code == "anonymous_registration_disabled"


def test_user_before_create_requires_precreated_id_from_service():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True}
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }

    with pytest.raises(ValidationError, match="Field 'id' must be a non-empty string"):
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload=payload,
                actor=None,
            )
        )


def test_user_before_create_rejects_when_default_group_missing():
    node_repo = InMemoryNodeRepo(users_docs=[])
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u1",
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }

    with pytest.raises(DefaultGroupNotFoundError, match="Default group with is_default=true not found") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload=payload,
                actor={"role": "superuser"},
            )
        )
    assert exc_info.value.code == "default_group_not_found"


def test_user_before_create_uses_one_of_multiple_default_groups():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default-1", "entity": "group", "deleted": False, "groupname": "default", "is_default": True},
            {"id": "g-default-2", "entity": "group", "deleted": False, "groupname": "default-2", "is_default": True},
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "id": "u1",
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
    }

    hooks.before_create(
        NodeHookContext(
            event="before_create",
            module="users",
            entity="user",
            payload=payload,
            actor={"user_id": "root", "role": "superuser", "primary_group": "g-default-1"},
        )
    )

    assert payload["primary_group"] in {"g-default-1", "g-default-2"}
    assert payload["groups"] == [payload["primary_group"]]

def test_user_before_create_rejects_admin_role_for_non_superuser():
    node_repo = InMemoryNodeRepo()
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "username": "alice",
        "password": "Abcd1234!",
        "groups": [],
        "connectors": [],
        "role": "admin",
    }
    context = NodeHookContext(
        event="before_create",
        module="users",
        entity="user",
        payload=payload,
        actor=None,
    )

    with pytest.raises(RoleAssignmentForbiddenError) as exc_info:
        hooks.before_create(context)
    assert exc_info.value.code == "role_assignment_forbidden"
    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["role"],
                "message": "Only a superuser can assign this role",
                "keyword": "role_assignment_forbidden",
            }
        ]
    }


def test_user_before_patch_enforces_unique_username_and_primary_group_membership():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {
                "id": "u2",
                "entity": "user",
                "deleted": False,
                "username": "bob",
            },
            {"id": "g1", "entity": "group", "deleted": False, "groupname": "g1"},
            {"id": "g2", "entity": "group", "deleted": False, "groupname": "g2"},
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(UsernameAlreadyExistsError) as exc_info:
        hooks.before_patch(
            NodeHookContext(
                event="before_patch",
                module="users",
                entity="user",
                node_id="u1",
                payload={"username": "bob"},
                current={"id": "u1", "groups": ["g1"], "primary_group": "g1"},
                actor={"role": "superuser"},
            )
        )
    assert exc_info.value.code == "username_already_exists"
    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["username"],
                "message": "Username is already in use",
                "keyword": "username_already_exists",
            }
        ]
    }

    payload = {"groups": ["g1"], "primary_group": "g2"}
    hooks.before_patch(
        NodeHookContext(
            event="before_patch",
            module="users",
            entity="user",
            node_id="u1",
            payload=payload,
            current={"id": "u1", "groups": ["g1"], "primary_group": "g1"},
            actor={"role": "superuser"},
        )
    )
    assert payload["groups"] == ["g1", "g2"]


def test_user_before_create_returns_specific_conflict_codes_for_username_and_email():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "u-existing", "entity": "user", "deleted": False, "username": "alice", "email": "alice@example.com"},
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True},
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(UsernameAlreadyExistsError) as username_exc:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={
                    "id": "u-new",
                    "username": "alice",
                    "password": "Abcd1234!",
                    "groups": [],
                    "connectors": [],
                },
                actor={"user_id": "root", "role": "superuser", "primary_group": "g-default", "groups": ["g-default"]},
            )
        )
    assert username_exc.value.code == "username_already_exists"
    assert username_exc.value.details == {
        "field_errors": [
            {
                "location": ["username"],
                "message": "Username is already in use",
                "keyword": "username_already_exists",
            }
        ]
    }

    with pytest.raises(EmailAlreadyExistsError) as email_exc:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={
                    "id": "u-new",
                    "username": "bob",
                    "email": "alice@example.com",
                    "password": "Abcd1234!",
                    "groups": [],
                    "connectors": [],
                },
                actor={"user_id": "root", "role": "superuser", "primary_group": "g-default", "groups": ["g-default"]},
            )
        )
    assert email_exc.value.code == "email_already_exists"
    assert email_exc.value.details == {
        "field_errors": [
            {
                "location": ["email"],
                "message": "Email is already in use",
                "keyword": "email_already_exists",
            }
        ]
    }


def test_user_before_create_reserves_username_and_email_of_soft_deleted_user():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {
                "id": "u-deleted",
                "entity": "user",
                "deleted": True,
                "username": "alice",
                "email": "alice@example.com",
            },
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True},
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    actor = {"user_id": "root", "role": "superuser", "primary_group": "g-default", "groups": ["g-default"]}

    with pytest.raises(UsernameAlreadyExistsError):
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={"id": "u-new", "username": "alice", "groups": []},
                actor=actor,
            )
        )

    with pytest.raises(EmailAlreadyExistsError):
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={"id": "u-new", "username": "bob", "email": "alice@example.com", "groups": []},
                actor=actor,
            )
        )


def test_user_before_create_returns_specific_code_for_invalid_email():
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": "g-default", "entity": "group", "deleted": False, "groupname": "default", "is_default": True},
        ]
    )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(EmailInvalidError, match="Field 'email' domain must include a top-level domain") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload={
                    "id": "u-new",
                    "username": "bob",
                    "email": "alice@localhost",
                    "password": "Abcd1234!",
                    "groups": [],
                    "connectors": [],
                },
                actor={"user_id": "root", "role": "superuser", "primary_group": "g-default", "groups": ["g-default"]},
            )
        )
    assert exc_info.value.code == "email_invalid"
    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["email"],
                "message": "Field 'email' domain must include a top-level domain",
                "keyword": "email_invalid",
            }
        ]
    }


def test_user_before_create_rejects_missing_or_deleted_group():
    node_repo = InMemoryNodeRepo(users_docs=[])
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "username": "alice",
        "password": "Abcd1234!",
        "primary_group": "g-missing",
        "groups": ["g-missing"],
        "connectors": [],
    }

    with pytest.raises(UserGroupNotFoundError, match="Group 'g-missing' not found or deleted") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload=payload,
                actor={"role": "superuser"},
            )
        )
    assert exc_info.value.code == "user_group_not_found"
    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["primary_group"],
                "message": "Selected group does not exist",
                "keyword": "user_group_not_found",
            }
        ]
    }


def test_user_before_patch_rejects_missing_group():
    node_repo = InMemoryNodeRepo(
            users_docs=[
                {"id": "g1", "entity": "group", "deleted": False, "groupname": "g1"},
            ]
        )
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {"primary_group": "g1", "groups": ["g1", "g-missing"]}

    with pytest.raises(UserGroupNotFoundError, match="Group 'g-missing' not found or deleted") as exc_info:
        hooks.before_patch(
            NodeHookContext(
                event="before_patch",
                module="users",
                entity="user",
                payload=payload,
                current={"id": "u1", "primary_group": "g1", "groups": ["g1"]},
                actor={"role": "superuser"},
            )
        )
    assert exc_info.value.code == "user_group_not_found"
    assert exc_info.value.details == {
        "field_errors": [
            {
                "location": ["groups"],
                "message": "One of the selected groups does not exist",
                "keyword": "user_group_not_found",
            }
        ]
    }


def test_user_before_create_rejects_direct_password_hash():
    node_repo = InMemoryNodeRepo()
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {
        "username": "alice",
        "password": "Abcd1234!",
        "password_hash": "raw-or-foreign-hash",
        "groups": [],
        "connectors": [],
    }

    with pytest.raises(PasswordHashDirectWriteForbiddenError, match="password_hash") as exc_info:
        hooks.before_create(
            NodeHookContext(
                event="before_create",
                module="users",
                entity="user",
                payload=payload,
            )
        )
    assert exc_info.value.code == "password_hash_direct_write_forbidden"
    assert exc_info.value.details is None


def test_user_before_patch_rejects_direct_password_hash():
    node_repo = InMemoryNodeRepo()
    hooks = UsersUserNodeHooks(node_repo, StubModuleRepo(), StubSecurity(), {})
    payload = {"password_hash": "raw-or-foreign-hash"}

    with pytest.raises(PasswordHashDirectWriteForbiddenError, match="password_hash") as exc_info:
        hooks.before_patch(
            NodeHookContext(
                event="before_patch",
                module="users",
                entity="user",
                payload=payload,
                current={"id": "u1"},
            )
        )
    assert exc_info.value.code == "password_hash_direct_write_forbidden"


def test_user_before_patch_ignores_empty_password():
    hooks = UsersUserNodeHooks(InMemoryNodeRepo(), StubModuleRepo(), StubSecurity(), {})
    payload = {"password": "", "username": " Alice "}

    hooks.before_patch(
        NodeHookContext(
            event="before_patch",
            module="users",
            entity="user",
            payload=payload,
            current={"id": "u1"},
        )
    )

    assert payload == {"username": "alice"}


def test_user_before_delete_rejects_active_node_owned_by_user_outside_subtree():
    user_id = "u-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": user_id, "entity": "user", "deleted": False, "owner": user_id, "ancestors": []},
            {"id": "dependent", "entity": "group", "deleted": False, "owner": user_id, "ancestors": []},
        ]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_owner": "other"}
    hooks = UsersUserNodeHooks(node_repo, module_repo, StubSecurity(), {})

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="user",
                node_id=user_id,
                current={"id": user_id},
            )
        )

    assert exc_info.value.code == "identity_in_use"
    assert exc_info.value.details == {
        "identity_type": "user",
        "identity_id": user_id,
        "reference_type": "node.owner",
        "module": "users",
        "node_id": "dependent",
    }


def test_user_before_delete_rejects_self_deletion_before_reference_checks():
    user_id = "u-delete"
    hooks = UsersUserNodeHooks(InMemoryNodeRepo(), StubModuleRepo(), StubSecurity(), {})

    with pytest.raises(SelfDeletionForbiddenError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="user",
                node_id=user_id,
                actor={"user_id": user_id},
                current={"id": user_id, "role": "all"},
            )
        )

    assert exc_info.value.code == "self_deletion_forbidden"


def test_users_before_delete_subtree_rejects_removing_last_superuser():
    user_id = "u-superuser"
    hooks = UsersUserNodeHooks(
        InMemoryNodeRepo(
            users_docs=[{"id": user_id, "entity": "user", "role": "superuser", "active": True, "deleted": False, "ancestors": []}]
        ),
        StubModuleRepo(),
        StubSecurity(),
        {},
    )

    with pytest.raises(LastSuperuserDeletionForbiddenError) as exc_info:
        hooks.before_delete_subtree(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id=user_id,
                current={"id": user_id},
            )
        )

    assert exc_info.value.code == "last_superuser_deletion_forbidden"


def test_users_before_delete_subtree_allows_removing_superuser_when_another_remains():
    hooks = UsersUserNodeHooks(
        InMemoryNodeRepo(
            users_docs=[
                {"id": "u-delete", "entity": "user", "role": "superuser", "active": True, "deleted": False, "ancestors": []},
                {"id": "u-remaining", "entity": "user", "role": "superuser", "active": True, "deleted": False, "ancestors": []},
            ]
        ),
        StubModuleRepo(),
        StubSecurity(),
        {},
    )

    hooks.before_delete_subtree(
        NodeHookContext(
            event="before_delete",
            module="users",
            entity="user",
            node_id="u-delete",
            current={"id": "u-delete"},
        )
    )


def test_users_before_delete_subtree_does_not_count_inactive_superuser():
    hooks = UsersUserNodeHooks(
        InMemoryNodeRepo(
            users_docs=[
                {"id": "u-delete", "entity": "user", "role": "superuser", "active": True, "deleted": False, "ancestors": []},
                {"id": "u-inactive", "entity": "user", "role": "superuser", "active": False, "deleted": False, "ancestors": []},
            ]
        ),
        StubModuleRepo(),
        StubSecurity(),
        {},
    )

    with pytest.raises(LastSuperuserDeletionForbiddenError):
        hooks.before_delete_subtree(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="user",
                node_id="u-delete",
                current={"id": "u-delete"},
            )
        )


def test_users_before_delete_subtree_rejects_parent_delete_that_removes_last_superuser():
    hooks = UsersUserNodeHooks(
        InMemoryNodeRepo(
            users_docs=[
                {"id": "parent", "entity": "group", "deleted": False, "ancestors": []},
                {
                    "id": "u-superuser",
                    "entity": "user",
                    "role": "superuser",
                    "active": True,
                    "deleted": False,
                    "ancestors": ["parent"],
                },
            ]
        ),
        StubModuleRepo(),
        StubSecurity(),
        {},
    )

    with pytest.raises(LastSuperuserDeletionForbiddenError):
        hooks.before_delete_subtree(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id="parent",
                current={"id": "parent"},
            )
        )


def test_user_before_delete_ignores_self_and_descendants_owned_by_user():
    user_id = "u-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": user_id, "entity": "user", "deleted": False, "owner": user_id, "ancestors": []},
            {
                "id": "descendant",
                "entity": "group",
                "deleted": False,
                "owner": user_id,
                "ancestors": [user_id],
            },
        ]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_owner": "other"}
    hooks = UsersUserNodeHooks(node_repo, module_repo, StubSecurity(), {})

    hooks.before_delete(
        NodeHookContext(
            event="before_delete",
            module="users",
            entity="user",
            node_id=user_id,
            current={"id": user_id},
        )
    )


def test_user_before_delete_rejects_module_root_owner_reference():
    user_id = "u-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[{"id": user_id, "entity": "user", "deleted": False, "owner": user_id, "ancestors": []}]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_owner": user_id}
    hooks = UsersUserNodeHooks(node_repo, module_repo, StubSecurity(), {})

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="user",
                node_id=user_id,
                current={"id": user_id},
            )
        )

    assert exc_info.value.details == {
        "identity_type": "user",
        "identity_id": user_id,
        "reference_type": "module.root_owner",
        "module": "users",
    }


def test_group_before_create_forces_is_default_false():
    hooks = UsersGroupNodeHooks(InMemoryNodeRepo(), StubModuleRepo())
    payload = {"groupname": "team", "is_default": True}
    hooks.before_create(
        NodeHookContext(
            event="before_create",
            module="users",
            entity="group",
            payload=payload,
        )
    )
    assert payload["is_default"] is False


def test_group_before_patch_ignores_is_default():
    hooks = UsersGroupNodeHooks(InMemoryNodeRepo(), StubModuleRepo())
    payload = {"is_default": True, "groupname": "team-updated"}
    hooks.before_patch(
        NodeHookContext(
            event="before_patch",
            module="users",
            entity="group",
            payload=payload,
        )
    )
    assert "is_default" not in payload
    assert payload["groupname"] == "team-updated"


def test_group_before_delete_rejects_default_group():
    hooks = UsersGroupNodeHooks(InMemoryNodeRepo(), StubModuleRepo())

    with pytest.raises(DefaultGroupDeletionForbiddenError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id="g-default",
                current={"id": "g-default", "is_default": True},
            )
        )

    assert exc_info.value.code == "default_group_deletion_forbidden"


def test_group_before_delete_rejects_active_node_group_reference():
    group_id = "g-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": group_id, "entity": "group", "deleted": False, "group": group_id, "ancestors": []},
            {"id": "dependent", "entity": "group", "deleted": False, "group": group_id, "ancestors": []},
        ]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_group": "other"}
    hooks = UsersGroupNodeHooks(node_repo, module_repo)

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id=group_id,
                current={"id": group_id, "is_default": False},
            )
        )

    assert exc_info.value.details == {
        "identity_type": "group",
        "identity_id": group_id,
        "reference_type": "node.group",
        "module": "users",
        "node_id": "dependent",
    }


def test_group_before_delete_rejects_user_primary_group_reference():
    group_id = "g-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": group_id, "entity": "group", "deleted": False, "group": group_id, "ancestors": []},
            {
                "id": "user-dependent",
                "entity": "user",
                "deleted": False,
                "primary_group": group_id,
                "groups": [group_id],
                "ancestors": [],
            },
        ]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_group": "other"}
    hooks = UsersGroupNodeHooks(node_repo, module_repo)

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id=group_id,
                current={"id": group_id, "is_default": False},
            )
        )

    assert exc_info.value.details == {
        "identity_type": "group",
        "identity_id": group_id,
        "reference_type": "user.primary_group",
        "module": "users",
        "node_id": "user-dependent",
    }


def test_group_before_delete_rejects_user_secondary_group_reference():
    group_id = "g-delete"
    node_repo = InMemoryNodeRepo(
        users_docs=[
            {"id": group_id, "entity": "group", "deleted": False, "group": group_id, "ancestors": []},
            {
                "id": "user-dependent",
                "entity": "user",
                "deleted": False,
                "primary_group": "g-primary",
                "groups": ["g-primary", group_id],
                "ancestors": [],
            },
        ]
    )
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_group": "other"}
    hooks = UsersGroupNodeHooks(node_repo, module_repo)

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id=group_id,
                current={"id": group_id, "is_default": False},
            )
        )

    assert exc_info.value.details == {
        "identity_type": "group",
        "identity_id": group_id,
        "reference_type": "user.groups",
        "module": "users",
        "node_id": "user-dependent",
    }


def test_group_before_delete_rejects_module_root_group_reference():
    group_id = "g-delete"
    module_repo = StubModuleRepo()
    module_repo.docs["users"] = {"name": "users", "root_group": group_id}
    hooks = UsersGroupNodeHooks(InMemoryNodeRepo(), module_repo)

    with pytest.raises(IdentityInUseError) as exc_info:
        hooks.before_delete(
            NodeHookContext(
                event="before_delete",
                module="users",
                entity="group",
                node_id=group_id,
                current={"id": group_id, "is_default": False},
            )
        )

    assert exc_info.value.details == {
        "identity_type": "group",
        "identity_id": group_id,
        "reference_type": "module.root_group",
        "module": "users",
    }


def test_user_hash_field_uses_none_access_mode():
    user = user_schema()

    user_hash_meta = user["properties"]["password_hash"]["anyOf"][0]["x-meta"]

    assert user_hash_meta["visibility-mode"] == "none"
    assert user_hash_meta["write-mode"] == "none"


def test_user_password_field_is_a_writable_transient_form_field():
    user = user_schema()

    password_meta = user["properties"]["password"]["x-meta"]

    assert "password" not in user["required"]
    assert password_meta["semantic-type"] == "Password"
    assert password_meta["visibility-mode"] == "all"
    assert password_meta["write-mode"] == "all"


def test_user_schema_uses_password_and_username_bootstrap_policy():
    schema = user_schema(
        {
            "AUTH_PASSWORD_MIN_LENGTH": 12,
            "AUTH_PASSWORD_PATTERN": r"^(?=.*[A-Z])(?=.*\d).+$",
            "AUTH_USERNAME_MIN_LENGTH": 5,
            "AUTH_USERNAME_MAX_LENGTH": 24,
            "AUTH_USERNAME_PATTERN": r"^[a-z]+$",
        }
    )

    password = schema["properties"]["password"]
    username = schema["properties"]["username"]
    assert password["minLength"] == 12
    assert password["pattern"] == r"^(?=.*[A-Z])(?=.*\d).+$"
    assert username["minLength"] == 5
    assert username["maxLength"] == 24
    assert username["pattern"] == r"^[a-z]+$"


def test_user_schema_rejects_invalid_bootstrap_policy():
    with pytest.raises(ValidationError, match="AUTH_PASSWORD_PATTERN"):
        user_schema({"AUTH_PASSWORD_PATTERN": "("})

    with pytest.raises(ValidationError, match="AUTH_USERNAME_MAX_LENGTH"):
        user_schema({"AUTH_USERNAME_MIN_LENGTH": 8, "AUTH_USERNAME_MAX_LENGTH": 7})


def test_group_schema_access_modes_match_spec():
    schema = group_schema()

    assert schema["properties"]["groupname"]["x-meta"]["visibility-mode"] == "all"
    assert schema["properties"]["groupname"]["x-meta"]["write-mode"] == "admin"
    assert schema["properties"]["is_default"]["x-meta"]["visibility-mode"] == "admin"
    assert schema["properties"]["is_default"]["x-meta"]["write-mode"] == "admin"


def test_users_system_schemas_define_tree_and_reference_labels():
    assert group_schema()["x-ui"]["labels"] == {
        "tree": "📁 {{groupname}}",
        "reference": "📁 {{groupname}}",
    }
    assert user_schema()["x-ui"]["labels"] == {
        "tree": "👤 {{username}}",
        "reference": "👤 {{username}}",
    }


def test_user_group_fields_use_superuser_access_mode():
    schema = user_schema()

    assert schema["properties"]["primary_group"]["x-meta"]["visibility-mode"] == "admin"
    assert schema["properties"]["primary_group"]["x-meta"]["write-mode"] == "superuser"
    assert schema["properties"]["groups"]["x-meta"]["visibility-mode"] == "admin"
    assert schema["properties"]["groups"]["x-meta"]["write-mode"] == "superuser"


def test_ensure_users_module_bootstrap_creates_group_and_root_user():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    ensure_users_module(
        module_repo,
        entity_service,
        node_repo,
        config={
            "ROOT_USERNAME": "admin",
            "ROOT_PASSWORD": "Admin123!",
            "DEFAULT_GROUP_GROUPNAME": "default",
        },
    )

    assert ("users", "group") in entity_service.created
    assert ("users", "user") in entity_service.created

    default_group = node_repo.find_one(
        "users",
        {"entity": "group", "deleted": False, "groupname": "default"},
        {"_id": 0},
    )
    root_user = node_repo.find_one(
        "users",
        {"entity": "user", "deleted": False, "username": "admin"},
        {"_id": 0},
    )
    assert default_group is not None
    assert root_user is not None
    assert root_user["primary_group"] == default_group["id"]
    assert root_user["groups"] == [default_group["id"]]
    assert module_repo.docs["users"]["root_children_entities"] == []
    assert node_repo.indexed_modules == ["users"]


def test_ensure_users_module_bootstrap_is_idempotent():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()
    cfg = {
        "ROOT_USERNAME": "admin",
        "ROOT_PASSWORD": "Admin123!",
        "DEFAULT_GROUP_GROUPNAME": "default",
    }

    ensure_users_module(module_repo, entity_service, node_repo, config=cfg)
    ensure_users_module(module_repo, entity_service, node_repo, config=cfg)

    groups = [d for d in node_repo.collection("users").docs if d.get("entity") == "group" and not d.get("deleted")]
    users = [d for d in node_repo.collection("users").docs if d.get("entity") == "user" and not d.get("deleted")]
    assert len(groups) == 1
    assert len(users) == 1


def test_ensure_users_module_does_not_reapply_policy_config_after_schema_is_created():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()
    cfg = {
        "ROOT_USERNAME": "admin",
        "ROOT_PASSWORD": "Admin123!",
        "DEFAULT_GROUP_GROUPNAME": "default",
    }

    ensure_users_module(module_repo, entity_service, node_repo, config=cfg)
    stored_schema = entity_service.schemas[("users", "user")]

    ensure_users_module(
        module_repo,
        entity_service,
        node_repo,
        config={"AUTH_PASSWORD_PATTERN": "("},
    )

    assert entity_service.schemas[("users", "user")] is stored_schema


def test_ensure_users_module_bootstrap_does_not_require_root_password_after_initialization():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()
    bootstrap_cfg = {
        "ROOT_USERNAME": "admin",
        "ROOT_PASSWORD": "Admin123!",
        "DEFAULT_GROUP_GROUPNAME": "default",
    }

    ensure_users_module(module_repo, entity_service, node_repo, config=bootstrap_cfg)
    ensure_users_module(
        module_repo,
        entity_service,
        node_repo,
        config={
            "ROOT_USERNAME": "admin",
            "DEFAULT_GROUP_GROUPNAME": "default",
        },
    )

    groups = [d for d in node_repo.collection("users").docs if d.get("entity") == "group" and not d.get("deleted")]
    users = [d for d in node_repo.collection("users").docs if d.get("entity") == "user" and not d.get("deleted")]
    assert len(groups) == 1
    assert len(users) == 1


def test_ensure_users_module_bootstrap_sets_system_acl_and_hashes_password():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    ensure_users_module(
        module_repo,
        entity_service,
        node_repo,
        config={
            "ROOT_USERNAME": "admin",
            "ROOT_PASSWORD": "Admin123!",
            "DEFAULT_GROUP_GROUPNAME": "default",
        },
    )

    group_node = node_repo.find_one("users", {"entity": "group", "deleted": False}, {"_id": 0})
    user_node = node_repo.find_one("users", {"entity": "user", "deleted": False}, {"_id": 0})
    assert group_node is not None
    assert user_node is not None

    assert group_node["owner"] == user_node["id"]
    assert group_node["group"] == group_node["id"]
    assert isinstance(group_node.get("perm"), dict)
    assert group_node["depth"] == 0
    assert group_node["ancestors"] == []
    assert group_node["deleted"] is False

    assert user_node["owner"] == user_node["id"]
    assert user_node["group"] == group_node["id"]
    assert isinstance(user_node.get("perm"), dict)
    assert user_node["depth"] == 0
    assert user_node["ancestors"] == []
    assert user_node["deleted"] is False
    assert isinstance(user_node.get("password_hash"), str)
    assert user_node["password_hash"]
    assert user_node["password_hash"] != "Admin123!"


def test_ensure_users_module_stores_schema_with_configured_credentials_policy():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    ensure_users_module(
        module_repo,
        entity_service,
        node_repo,
        config={
            "ROOT_USERNAME": "admin",
            "ROOT_PASSWORD": "Secret-12345",
            "DEFAULT_GROUP_GROUPNAME": "default",
            "AUTH_PASSWORD_MIN_LENGTH": 12,
            "AUTH_PASSWORD_PATTERN": r"^(?=.*-).+$",
            "AUTH_USERNAME_MIN_LENGTH": 4,
            "AUTH_USERNAME_MAX_LENGTH": 16,
            "AUTH_USERNAME_PATTERN": r"^[a-z]+$",
        },
    )

    properties = entity_service.schemas[("users", "user")]["properties"]
    assert properties["password"]["minLength"] == 12
    assert properties["password"]["pattern"] == r"^(?=.*-).+$"
    assert properties["username"]["minLength"] == 4
    assert properties["username"]["maxLength"] == 16
    assert properties["username"]["pattern"] == r"^[a-z]+$"


def test_ensure_users_module_rejects_empty_root_password():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    with pytest.raises(ValidationError, match="Bootstrap config 'ROOT_PASSWORD' must be a non-empty string"):
        ensure_users_module(
            module_repo,
            entity_service,
            node_repo,
            config={
                "ROOT_USERNAME": "admin",
                "ROOT_PASSWORD": "",
                "DEFAULT_GROUP_GROUPNAME": "default",
            },
        )


def test_ensure_users_module_validates_root_password_against_users_schema():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    with pytest.raises(ValidationError, match="Bootstrap ROOT_PASSWORD does not satisfy users/user.password schema"):
        ensure_users_module(
            module_repo,
            entity_service,
            node_repo,
            config={
                "ROOT_USERNAME": "admin",
                "ROOT_PASSWORD": "Abcd1234",
                "DEFAULT_GROUP_GROUPNAME": "default",
            },
        )


def test_ensure_users_module_applies_username_policy_to_root_username():
    module_repo = StubModuleRepo()
    entity_service = StubEntityService()
    node_repo = InMemoryNodeRepo()

    with pytest.raises(ValidationError, match="Bootstrap ROOT_USERNAME does not satisfy users/user.username schema"):
        ensure_users_module(
            module_repo,
            entity_service,
            node_repo,
            config={
                "ROOT_USERNAME": "admin root",
                "ROOT_PASSWORD": "Admin123!",
                "DEFAULT_GROUP_GROUPNAME": "default",
            },
        )
