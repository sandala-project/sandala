from __future__ import annotations

import re
from typing import Any

from sandala.config import DEFAULT_CONFIG
from sandala.core.errors import ValidationError

USER_MODULE = "users"
USER_ENTITY = "user"
GROUP_ENTITY = "group"
USER_PROTECTED_FIELDS = (
    "username",
    "email",
    "primary_group",
    "groups",
    "password",
    "password_hash",
    "role",
    "active",
)
GROUP_PROTECTED_FIELDS = (
    "groupname",
    "is_default",
)

_DEFAULT_ENTITY_PERM = {
    "owner": {"r": True, "w": True, "p": True},
    "group": {"r": True, "w": False, "p": False},
    "others": {"r": True, "w": False, "p": False},
}


def group_schema() -> dict:
    return {
        "title": GROUP_ENTITY,
        "description": "",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groupname": {
                "type": "string",
                "minLength": 1,
                "x-meta": {
                    "semantic-type": "String",
                    "visibility-mode": "all",
                    "write-mode": "admin",
                },
            },
            "is_default": {
                "type": "boolean",
                "x-meta": {
                    "semantic-type": "Boolean",
                    "visibility-mode": "admin",
                    "write-mode": "admin",
                },
            },
        },
        "required": ["groupname", "is_default"],
        "x-ui": {
            "labels": {
                "tree": "📁 {{groupname}}",
                "reference": "📁 {{groupname}}",
            },
        },
        "x-meta": {
            "children": {"entities": []},
            "perm": {"default": _DEFAULT_ENTITY_PERM},
        },
    }


def user_schema(config: dict[str, Any] | None = None) -> dict:
    cfg = config or {}
    password_min_length = _read_integer_config(
        cfg,
        "AUTH_PASSWORD_MIN_LENGTH",
        default=DEFAULT_CONFIG["AUTH_PASSWORD_MIN_LENGTH"],
        minimum=0,
    )
    password_pattern = _read_required_pattern(
        cfg,
        "AUTH_PASSWORD_PATTERN",
        default=DEFAULT_CONFIG["AUTH_PASSWORD_PATTERN"],
    )
    username_min_length = _read_integer_config(
        cfg,
        "AUTH_USERNAME_MIN_LENGTH",
        default=DEFAULT_CONFIG["AUTH_USERNAME_MIN_LENGTH"],
        minimum=1,
    )
    username_max_length = _read_integer_config(
        cfg,
        "AUTH_USERNAME_MAX_LENGTH",
        default=DEFAULT_CONFIG["AUTH_USERNAME_MAX_LENGTH"],
        minimum=1,
    )
    if username_max_length < username_min_length:
        raise ValidationError(
            "Config 'AUTH_USERNAME_MAX_LENGTH' must be greater than or equal to AUTH_USERNAME_MIN_LENGTH"
        )
    username_pattern = _read_required_pattern(
        cfg,
        "AUTH_USERNAME_PATTERN",
        default=DEFAULT_CONFIG["AUTH_USERNAME_PATTERN"],
    )

    password_field: dict[str, Any] = {
        "type": "string",
        "minLength": password_min_length,
        "pattern": password_pattern,
        "x-meta": {
            "semantic-type": "Password",
            "visibility-mode": "all",
            "write-mode": "all",
        },
    }
    return {
        "title": USER_ENTITY,
        "description": "",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "username": {
                "type": "string",
                "minLength": username_min_length,
                "maxLength": username_max_length,
                "pattern": username_pattern,
                "x-meta": {
                    "semantic-type": "String",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            },
            "email": {
                "anyOf": [
                    {
                        "type": "string",
                        "x-meta": {
                            "semantic-type": "String",
                            "visibility-mode": "admin",
                            "write-mode": "admin",
                        },
                    },
                    {"type": "null"},
                ]
            },
            "primary_group": {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": "Link",
                    "visibility-mode": "admin",
                    "write-mode": "superuser",
                    "link": {"module": USER_MODULE, "entities": [GROUP_ENTITY]},
                },
            },
            "groups": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "minItems": 1,
                "x-meta": {
                    "semantic-type": "LinkArray",
                    "visibility-mode": "admin",
                    "write-mode": "superuser",
                    "link": {"module": USER_MODULE, "entities": [GROUP_ENTITY]},
                },
            },
            "password": password_field,
            "password_hash": {
                "anyOf": [
                    {
                        "type": "string",
                        "x-meta": {
                            "semantic-type": "String",
                            "visibility-mode": "none",
                            "write-mode": "none",
                        },
                    },
                    {"type": "null"},
                ]
            },
            "role": {
                "type": "string",
                "enum": ["superuser", "admin", "all"],
                "x-meta": {
                    "semantic-type": "String",
                    "visibility-mode": "admin",
                    "write-mode": "admin",
                },
            },
            "active": {
                "type": "boolean",
                "x-meta": {
                    "semantic-type": "Boolean",
                    "visibility-mode": "admin",
                    "write-mode": "admin",
                },
            },
        },
        "required": ["username", "primary_group", "groups", "role", "active"],
        "x-ui": {
            "labels": {
                "tree": "👤 {{username}}",
                "reference": "👤 {{username}}",
            },
        },
        "x-meta": {
            "children": {"entities": []},
            "perm": {"default": _DEFAULT_ENTITY_PERM},
        },
    }


def _read_integer_config(
    config: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"Config '{key}' must be an integer greater than or equal to {minimum}")
    return value


def _read_required_pattern(config: dict[str, Any], key: str, *, default: str) -> str:
    value = config.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Config '{key}' must be a non-empty string")
    _validate_pattern(value, key=key)
    return value


def _validate_pattern(value: str, *, key: str) -> None:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValidationError(f"Config '{key}' must be a valid regular expression") from exc
