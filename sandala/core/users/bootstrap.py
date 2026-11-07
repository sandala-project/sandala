from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from jsonschema import Draft7Validator

from sandala.core.errors import ValidationError
from sandala.core.security import SecurityService
from sandala.core.time_utils import utc_now_iso
from sandala.core.users.schemas import (
    GROUP_ENTITY,
    USER_ENTITY,
    USER_MODULE,
    group_schema,
    user_schema,
)


def ensure_users_module(module_repo, entity_repo, node_repo, config: dict[str, Any] | None = None) -> None:
    cfg = config or {}
    security = SecurityService()

    if not module_repo.module_exists(USER_MODULE):
        node_repo.ensure_module_indexes(USER_MODULE)

    _ensure_entity(entity_repo, USER_MODULE, GROUP_ENTITY, group_schema())
    if entity_repo.entity_exists(USER_MODULE, USER_ENTITY):
        users_schema = entity_repo.get_schema(USER_MODULE, USER_ENTITY)
        if not isinstance(users_schema, dict):
            raise ValidationError("Stored users/user schema is missing")
    else:
        users_schema = user_schema(cfg)
        _ensure_entity(entity_repo, USER_MODULE, USER_ENTITY, users_schema)

    root_username = _optional_config_str(cfg, "ROOT_USERNAME")
    if root_username is not None:
        root_username = _normalize_and_validate_bootstrap_username(security, users_schema, root_username)

    default_group_groupname = _optional_config_str(cfg, "DEFAULT_GROUP_GROUPNAME")
    if default_group_groupname is not None:
        default_group_groupname = default_group_groupname.lower()

    root_user = (
        _find_active_user_by_username(node_repo, root_username)
        if root_username is not None
        else _find_active_superuser(node_repo)
    )
    default_group = (
        _find_active_group_by_name(node_repo, default_group_groupname)
        if default_group_groupname is not None
        else _find_active_default_group(node_repo)
    )
    if root_user is None and default_group is None:
        root_username = _normalize_and_validate_bootstrap_username(
            security,
            users_schema,
            _required_config_str(cfg, "ROOT_USERNAME"),
        )
        root_password = _required_config_str(cfg, "ROOT_PASSWORD")
        _validate_bootstrap_user_field(users_schema, "password", root_password, config_key="ROOT_PASSWORD")
        root_user_id = str(uuid4())
        default_group_id = str(uuid4())
        root_user = _insert_bootstrap_user(
            node_repo,
            security=security,
            user_id=root_user_id,
            username=root_username,
            raw_password=root_password,
            primary_group_id=default_group_id,
        )
        default_group = _insert_bootstrap_group(
            node_repo,
            group_id=default_group_id,
            owner_id=root_user_id,
            groupname=_required_config_str(cfg, "DEFAULT_GROUP_GROUPNAME").lower(),
        )
    elif default_group is None:
        default_group = _insert_bootstrap_group(
            node_repo,
            group_id=str(uuid4()),
            owner_id=root_user["id"],
            groupname=_required_config_str(cfg, "DEFAULT_GROUP_GROUPNAME").lower(),
        )
    elif root_user is None:
        root_username = _normalize_and_validate_bootstrap_username(
            security,
            users_schema,
            _required_config_str(cfg, "ROOT_USERNAME"),
        )
        root_password = _required_config_str(cfg, "ROOT_PASSWORD")
        _validate_bootstrap_user_field(users_schema, "password", root_password, config_key="ROOT_PASSWORD")
        root_user = _insert_bootstrap_user(
            node_repo,
            security=security,
            user_id=str(uuid4()),
            username=root_username,
            raw_password=root_password,
            primary_group_id=default_group["id"],
        )
    _ensure_module(module_repo, root_owner=root_user["id"], root_group=default_group["id"])


def _ensure_entity(entity_repo, module: str, entity: str, schema: dict[str, Any]) -> None:
    if entity_repo.entity_exists(module, entity):
        return
    entity_repo.create(module, entity, schema)


def _ensure_module(module_repo, *, root_owner: str, root_group: str) -> None:
    if module_repo.module_exists(USER_MODULE):
        return
    module_repo.create_module(
        {
            "name": USER_MODULE,
            "description": "Users",
            "root_owner": root_owner,
            "root_group": root_group,
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
        }
    )


def _required_config_str(cfg: dict[str, Any], key: str) -> str:
    raw = cfg.get(key)
    if not isinstance(raw, str):
        raise ValidationError(f"Missing required bootstrap config '{key}'")
    value = raw.strip()
    if not value:
        raise ValidationError(f"Bootstrap config '{key}' must be a non-empty string")
    return value


def _optional_config_str(cfg: dict[str, Any], key: str) -> str | None:
    raw = cfg.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValidationError(f"Bootstrap config '{key}' must be a string")
    value = raw.strip()
    if not value:
        raise ValidationError(f"Bootstrap config '{key}' must be a non-empty string")
    return value


def _normalize_and_validate_bootstrap_username(
    security: SecurityService,
    users_schema: dict[str, Any],
    value: str,
) -> str:
    username = security.normalize_username(value, field_name="ROOT_USERNAME")
    _validate_bootstrap_user_field(users_schema, "username", username, config_key="ROOT_USERNAME")
    return username


def _validate_bootstrap_user_field(
    users_schema: dict[str, Any],
    field_name: str,
    value: str,
    *,
    config_key: str,
) -> None:
    properties = users_schema.get("properties")
    field_schema = properties.get(field_name) if isinstance(properties, dict) else None
    if not isinstance(field_schema, dict):
        raise ValidationError(f"Users schema has no '{field_name}' field")
    errors = sorted(Draft7Validator(field_schema).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise ValidationError(
            f"Bootstrap {config_key} does not satisfy users/{USER_ENTITY}.{field_name} schema: {errors[0].message}"
        )


def _find_active_group_by_name(node_repo, groupname: str) -> dict[str, Any] | None:
    doc = node_repo.find_one(
        USER_MODULE,
        {
            "entity": GROUP_ENTITY,
            "deleted": False,
            "groupname": groupname,
        },
        {"_id": 0},
    )
    if doc is None:
        return None
    return doc


def _find_active_default_group(node_repo) -> dict[str, Any] | None:
    doc = node_repo.find_one(
        USER_MODULE,
        {
            "entity": GROUP_ENTITY,
            "deleted": False,
            "is_default": True,
        },
        {"_id": 0},
    )
    if doc is None:
        return None
    return doc


def _find_active_user_by_username(node_repo, username: str) -> dict[str, Any] | None:
    doc = node_repo.find_one(
        USER_MODULE,
        {
            "entity": USER_ENTITY,
            "deleted": False,
            "username": username,
        },
        {"_id": 0},
    )
    if doc is None:
        return None
    return doc


def _find_active_superuser(node_repo) -> dict[str, Any] | None:
    doc = node_repo.find_one(
        USER_MODULE,
        {
            "entity": USER_ENTITY,
            "deleted": False,
            "role": "superuser",
            "active": True,
        },
        {"_id": 0},
    )
    if doc is None:
        return None
    return doc


def _default_perm_for(entity: str) -> dict[str, Any]:
    if entity == GROUP_ENTITY:
        source_schema = group_schema()
    elif entity == USER_ENTITY:
        source_schema = user_schema()
    else:
        raise ValueError(f"Unsupported bootstrap entity for default perm: {entity}")
    return deepcopy(source_schema["x-meta"]["perm"]["default"])


def _insert_bootstrap_group(
    node_repo,
    *,
    group_id: str,
    owner_id: str,
    groupname: str,
) -> dict[str, Any]:
    now = utc_now_iso()
    group_node = {
        "id": group_id,
        "entity": GROUP_ENTITY,
        "parent": None,
        "owner": owner_id,
        "group": group_id,
        "perm": _default_perm_for(GROUP_ENTITY),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": now,
        "mdate": now,
        "groupname": groupname,
        "is_default": True,
    }
    return node_repo.insert_node(USER_MODULE, group_node)


def _insert_bootstrap_user(
    node_repo,
    *,
    security: SecurityService,
    user_id: str,
    username: str,
    raw_password: str,
    primary_group_id: str,
) -> dict[str, Any]:
    now = utc_now_iso()
    user_node = {
        "id": user_id,
        "entity": USER_ENTITY,
        "parent": None,
        "owner": user_id,
        "group": primary_group_id,
        "perm": _default_perm_for(USER_ENTITY),
        "depth": 0,
        "ancestors": [],
        "deleted": False,
        "cdate": now,
        "mdate": now,
        "username": username,
        "email": None,
        "primary_group": primary_group_id,
        "groups": [primary_group_id],
        "password_hash": security.hash_password(raw_password),
        "role": "superuser",
        "active": True,
    }
    return node_repo.insert_node(USER_MODULE, user_node)
