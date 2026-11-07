from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SystemFieldSpec:
    name: str
    semantic_type: str
    synthetic_schema: dict[str, Any]


class SystemFieldProvider:
    def __init__(self) -> None:
        self._specs = {
            "_id": SystemFieldSpec(
                name="_id", semantic_type="String", synthetic_schema=_scalar_schema("String"),
            ),
            "entity": SystemFieldSpec(
                name="entity", semantic_type="String", synthetic_schema=_scalar_schema("String"),
            ),
            "depth": SystemFieldSpec(
                name="depth", semantic_type="Integer",
                synthetic_schema={"type": "integer", "x-meta": {"semantic-type": "Integer", "visibility-mode": "all"}},
            ),
            "deleted": SystemFieldSpec(
                name="deleted", semantic_type="Boolean",
                synthetic_schema={"type": "boolean", "x-meta": {"semantic-type": "Boolean", "visibility-mode": "all"}},
            ),
            "id": SystemFieldSpec(
                name="id",
                semantic_type="String",
                synthetic_schema=_scalar_schema("String"),
            ),
            "cdate": SystemFieldSpec(
                name="cdate",
                semantic_type="DateTime",
                synthetic_schema=_scalar_schema("DateTime"),
            ),
            "mdate": SystemFieldSpec(
                name="mdate",
                semantic_type="DateTime",
                synthetic_schema=_scalar_schema("DateTime"),
            ),
            "perm": SystemFieldSpec(
                name="perm",
                semantic_type="Object",
                synthetic_schema=_permission_schema(),
            ),
            "owner": SystemFieldSpec(
                name="owner",
                semantic_type="Link",
                synthetic_schema={
                    "type": "string",
                    "x-meta": {
                        "semantic-type": "Link",
                        "visibility-mode": "all",
                        "link": {"module": "users", "entities": ["user"]},
                    },
                },
            ),
            "group": SystemFieldSpec(
                name="group",
                semantic_type="Link",
                synthetic_schema={
                    "type": "string",
                    "x-meta": {
                        "semantic-type": "Link",
                        "visibility-mode": "all",
                        "link": {"module": "users", "entities": ["group"]},
                    },
                },
            ),
            "parent": SystemFieldSpec(
                name="parent",
                semantic_type="NodeParentRef",
                synthetic_schema={
                    "type": "string",
                    "x-meta": {
                        "semantic-type": "NodeParentRef",
                        "visibility-mode": "all",
                    },
                },
            ),
            "ancestors": SystemFieldSpec(
                name="ancestors",
                semantic_type="NodeAncestorsRef",
                synthetic_schema={
                    "type": "array",
                    "items": {"type": "string"},
                    "x-meta": {
                        "semantic-type": "NodeAncestorsRef",
                        "visibility-mode": "all",
                    },
                },
            ),
        }

    def get(self, field_name: str) -> SystemFieldSpec | None:
        return self._specs.get(field_name)


def _scalar_schema(semantic_type: str) -> dict[str, Any]:
    return {
        "type": "string",
        "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all"},
    }


def _permission_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "x-meta": {"semantic-type": "Object", "visibility-mode": "all"},
        "properties": {
            subject: {
                "type": "object",
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all"},
                "properties": {
                    permission: {
                        "type": "boolean",
                        "x-meta": {"semantic-type": "Boolean", "visibility-mode": "all"},
                    }
                    for permission in ("r", "w", "p")
                },
            }
            for subject in ("owner", "group", "others")
        },
    }
